"""Curate one pasted viral script inside a disposable dsh workspace."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import threading
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from services.copy_agent.audit import audit_tool_paths, harness_env
from services.copy_agent.card_schema import (
    card_preview_from_yaml,
    curate_schema_markdown,
    validate_analysis,
    validate_body_blocking,
    validate_body_warnings,
    validate_card,
)
from services.copy_agent.pattern_library import build_pattern_library_markdown
from services.copy_agent.fact_gate import trap_check
from services.copy_agent.progress import build_curate_progress, read_live_session_text
from services.copy_agent.session_log import last_turn_end_reason
from src.db.engine import get_session_factory
from src.db.models.playbook import CopyAgentJob, PatternCard, PlaybookVersion
from src.utils.paths import get_data_dir

Runner = Callable[[Path, Path, str, dict], None]

SUMMARY_OK = "这次只写了草稿目录里的文件。"
SUMMARY_ESCAPE = "这次写到了草稿目录外面，结果已丢弃。"
_SYSTEM_PROMPT = (
    "你只根据当前工作目录里的文件拆卡：先写 drafts/analysis.md，"
    "再写 drafts/card.yaml 与 drafts/playbook.diff.yaml。"
    "严格遵守 schema.md；除 evidence_excerpt 外不得复制 material 原句到模式卡。"
    "不要读取工作目录以外的文件。"
)

_CURATE_PROMPT_PHASE_A = (
    "【第一步】阅读 material.txt 与 schema.md。"
    "只创建并写入 drafts/analysis.md：标注 move 顺序、frame 显著点、动机推断。"
    "不要写 card.yaml 或 playbook.diff.yaml。"
)

_CURATE_PROMPT_PHASE_B = (
    "【第二步】阅读 drafts/analysis.md、schema.md、pattern_library.md（若存在）。"
    "写 drafts/card.yaml（抽象模式卡 v2）与 drafts/playbook.diff.yaml（body 写法说明）。"
    "material.txt 仅用于核对事实，不要把原句写进 card。"
)


def dsh_sdk_installed() -> bool:
    return importlib.util.find_spec("deepseek_harness") is not None


def start_dsh(workspace: Path, session_root: Path, session_id: str, env: dict) -> None:
    """Run DeepSeek Harness inside the curate workspace.

    The SDK launches its bundled dsh. Callers pass an allowlisted env.
    The first subprocess inherits that mapping; the parent process env stays.
    """
    import deepseek_harness

    child_env = dict(env)
    child_env["DSH_SYSTEM_PROMPT"] = _SYSTEM_PROMPT
    child_env["DSH_HOME"] = str(session_root.resolve())
    model = child_env.get("DEEPSEEK_MODEL") or "deepseek-v4-flash"
    # The SDK copies os.environ and then merges env=. Replace the first
    # Popen environment so the bundled dsh does not inherit other secrets.
    with _forced_subprocess_env(child_env):
        with deepseek_harness.DeepSeekHarness(
            provider="deepseek-official",
            model=model,
            max_tokens=16384,
            cwd=str(workspace.resolve()),
            dsh_home=str(session_root.resolve()),
            profile="sdk-minimal",
            env=child_env,
            request_timeout_seconds=180,
        ) as harness:
            harness.run(_CURATE_PROMPT_PHASE_A, session_id=session_id)
            harness.run(_CURATE_PROMPT_PHASE_B, session_id=f"{session_id}-b")
    _publish_session_log(session_root, session_root)


def begin_curate(
    session: Session,
    *,
    text: str,
    include_battle: bool = False,
) -> CopyAgentJob:
    job = CopyAgentJob(kind="curate", status="pending", session_id=None)
    session.add(job)
    session.flush()
    job.session_id = job.id

    cleaned = (text or "").strip()
    if not cleaned:
        job.status = "needs_text"
        session.commit()
        return job

    root = get_data_dir() / "copy_agent"
    workspace = root / "workspaces" / job.id
    session_root = root / "sessions" / job.id
    (workspace / "drafts").mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)
    _write_job_progress(
        session,
        job,
        session_root,
        workspace,
        phase="preparing",
        phase_label="正在准备草稿目录…",
    )
    (workspace / "material.txt").write_text(cleaned, encoding="utf-8")
    schema = curate_schema_markdown()
    if include_battle:
        _write_battle_report(session, workspace)
        schema += "\n若有 battle_report.md，只把它当作上一轮发布结果，不要把里面的数字写进打法正文。\n"
    (workspace / "schema.md").write_text(schema, encoding="utf-8")
    (workspace / "pattern_library.md").write_text(
        build_pattern_library_markdown(session), encoding="utf-8"
    )
    job.workspace_path = str(workspace)
    job.status = "running"
    _write_job_progress(
        session,
        job,
        session_root,
        workspace,
        phase="running",
        phase_label="智能体正在拆卡…",
    )
    session.commit()
    return job


def run_curate(
    session: Session,
    *,
    text: str,
    runner: Runner | None = None,
    include_battle: bool = False,
) -> CopyAgentJob:
    job = begin_curate(session, text=text, include_battle=include_battle)
    if job.status != "running":
        return job
    execute_curate_job(job.id, runner=runner or start_dsh)
    session.expire(job)
    return session.get(CopyAgentJob, job.id) or job


def fail_orphaned_curate_jobs(session: Session) -> int:
    """Mark curate jobs left in running after a process restart."""
    jobs = session.query(CopyAgentJob).filter_by(kind="curate", status="running").all()
    if not jobs:
        return 0
    for job in jobs:
        job.status = "failed"
        payload = _load_result(job)
        payload["summary"] = "拆卡已中断，请重新点击「拆成打法」。"
        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        progress.update(
            {
                "phase": "failed",
                "phase_label": "上次拆卡未正常结束（常见于重启服务）。",
            }
        )
        payload["progress"] = progress
        job.result_json = json.dumps(payload, ensure_ascii=False)
    session.commit()
    return len(jobs)


def execute_curate_job(job_id: str, *, runner: Runner | None = None) -> None:
    active = runner or start_dsh
    session = get_session_factory()()
    monitor_stop = threading.Event()
    monitor = _start_progress_monitor(job_id, monitor_stop)
    try:
        job = session.get(CopyAgentJob, job_id)
        if job is None or job.status != "running":
            return
        workspace = Path(job.workspace_path or "")
        session_root = get_data_dir() / "copy_agent" / "sessions" / job.id
        env = harness_env(dict(os.environ))
        try:
            active(workspace, session_root, job.id, env)
        finally:
            monitor_stop.set()
            monitor.join(timeout=5)
            _publish_session_log(session_root, session_root)
        _finalize_curate(session, job, workspace, session_root)
    except Exception as exc:
        session.rollback()
        _mark_curate_failed(job_id, str(exc))
    finally:
        session.close()


def _finalize_curate(session: Session, job: CopyAgentJob, workspace: Path, session_root: Path) -> None:
    _write_job_progress(
        session,
        job,
        session_root,
        workspace,
        phase="auditing",
        phase_label="正在核对是否只动了草稿目录…",
        log_text=read_live_session_text(session_root),
    )
    jsonl_text = read_live_session_text(session_root)
    escaped = audit_tool_paths(jsonl_text, [workspace, session_root])
    if escaped:
        job.status = "rejected_escape"
        payload = _load_result(job)
        payload.update({"summary": SUMMARY_ESCAPE, "paths": escaped})
        payload["progress"] = build_curate_progress(
            session_root,
            workspace,
            phase="failed",
            phase_label="草稿目录核对未通过，结果已丢弃。",
            log_text=jsonl_text,
        )
        job.result_json = json.dumps(payload, ensure_ascii=False)
        session.commit()
        return

    _write_job_progress(
        session,
        job,
        session_root,
        workspace,
        phase="validating",
        phase_label="正在检查模式卡和打法格式…",
        log_text=jsonl_text,
    )
    card_path = workspace / "drafts" / "card.yaml"
    diff_path = workspace / "drafts" / "playbook.diff.yaml"
    card = _load_yaml(card_path)
    diff = _load_yaml(diff_path)
    verdict = card.get("verdict") if isinstance(card.get("verdict"), dict) else {}
    cleaned = (workspace / "material.txt").read_text(encoding="utf-8") if (workspace / "material.txt").is_file() else ""
    body = str(diff.get("body") or "")
    analysis_path = workspace / "drafts" / "analysis.md"
    analysis_text = analysis_path.read_text(encoding="utf-8") if analysis_path.is_file() else ""
    schema_issues = _schema_issues(
        card_path,
        diff_path,
        card,
        diff,
        jsonl_text,
        material=cleaned,
        body=body,
        analysis_path=analysis_path,
        analysis_text=analysis_text,
    )
    if schema_issues:
        job.status = "rejected_schema"
        payload = _load_result(job)
        summary = _schema_summary(schema_issues)
        payload.update(
            {
                "summary": summary,
                "schema_issues": schema_issues,
                "turn_end_reason": last_turn_end_reason(jsonl_text),
            }
        )
        payload["progress"] = build_curate_progress(
            session_root,
            workspace,
            phase="failed",
            phase_label=summary,
            log_text=jsonl_text,
        )
        job.result_json = json.dumps(payload, ensure_ascii=False)
        session.commit()
        return

    body_warnings = validate_body_warnings(card, body)
    trap = trap_check(body)
    _write_job_progress(
        session,
        job,
        session_root,
        workspace,
        phase="storing",
        phase_label="正在写入候选打法…",
        log_text=jsonl_text,
    )
    version = PlaybookVersion(
        parent_id=None,
        body=body,
        diff_json=diff_path.read_text(encoding="utf-8"),
        status="candidate",
        trap_passed=bool(trap["passed"]),
    )
    session.add(version)
    session.flush()
    forbidden = card.get("transfer_rules", {}).get("forbidden_transfers") if isinstance(card.get("transfer_rules"), dict) else card.get("forbidden_transfers")
    if not isinstance(forbidden, list):
        forbidden = []
    session.add(
        PatternCard(
            source_job_id=job.id,
            status="draft",
            verdict_kind="opinion",
            verdict_function=str(verdict.get("function") or ""),
            forbidden_transfers_json=json.dumps(forbidden, ensure_ascii=False),
            evidence_excerpt=str(card.get("evidence_excerpt") or "").strip(),
            card_json=json.dumps(card, ensure_ascii=False),
        )
    )
    job.status = "candidate"
    payload = _load_result(job)
    payload.update(
        {
            "summary": SUMMARY_OK,
            "playbook_version_id": version.id,
            "trap_passed": version.trap_passed,
            "card_preview": card_preview_from_yaml(card),
            "playbook_body": body,
            "body_issues": body_warnings,
        }
    )
    payload["progress"] = build_curate_progress(
        session_root,
        workspace,
        phase="done",
        phase_label="拆卡完成，可以发布为当前打法。",
        log_text=jsonl_text,
    )
    job.result_json = json.dumps(payload, ensure_ascii=False)
    session.commit()


def _mark_curate_failed(job_id: str, message: str) -> None:
    session = get_session_factory()()
    try:
        job = session.get(CopyAgentJob, job_id)
        if job is None:
            return
        job.status = "failed"
        payload = _load_result(job)
        payload.update({"summary": "拆卡失败，请稍后重试。"})
        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        progress.update({"phase": "failed", "phase_label": message or "拆卡失败"})
        payload["progress"] = progress
        job.result_json = json.dumps(payload, ensure_ascii=False)
        session.commit()
    finally:
        session.close()


def _load_result(job: CopyAgentJob) -> dict:
    try:
        loaded = json.loads(job.result_json or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_job_progress(
    session: Session,
    job: CopyAgentJob,
    session_root: Path,
    workspace: Path,
    *,
    phase: str,
    phase_label: str,
    log_text: str | None = None,
) -> None:
    payload = _load_result(job)
    payload["progress"] = build_curate_progress(
        session_root,
        workspace,
        phase=phase,
        phase_label=phase_label,
        log_text=log_text,
    )
    job.result_json = json.dumps(payload, ensure_ascii=False)
    session.commit()


def _start_progress_monitor(job_id: str, stop_event: threading.Event) -> threading.Thread:
    def loop() -> None:
        while not stop_event.wait(2.0):
            session = get_session_factory()()
            try:
                job = session.get(CopyAgentJob, job_id)
                if job is None or job.status != "running":
                    return
                workspace = Path(job.workspace_path or "")
                session_root = get_data_dir() / "copy_agent" / "sessions" / job.id
                _write_job_progress(
                    session,
                    job,
                    session_root,
                    workspace,
                    phase="running",
                    phase_label="智能体正在拆卡…",
                )
            finally:
                session.close()

    thread = threading.Thread(target=loop, name=f"curate-progress-{job_id}", daemon=True)
    thread.start()
    return thread


def _write_battle_report(session: Session, workspace: Path) -> None:
    from services.copy_agent.battle_report import build_battle_report

    report = build_battle_report(session)
    lines = ["# 发布结果", ""]
    for row in report["learn_again"]:
        lines.append(
            f"- {row.get('platform') or ''} 转发 {row.get('share_count')} 赞 {row.get('like_count')}"
        )
    if len(lines) == 2:
        lines.append("（没有可再学的打法发布）")
    (workspace / "battle_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _schema_issues(
    card_path: Path,
    diff_path: Path,
    card: dict,
    diff: dict,
    jsonl_text: str,
    *,
    material: str = "",
    body: str = "",
    analysis_path: Path | None = None,
    analysis_text: str = "",
) -> list[str]:
    issues: list[str] = []
    if analysis_path is None or not analysis_path.is_file() or analysis_path.stat().st_size == 0:
        issues.append("未生成 drafts/analysis.md（两阶段拆卡第一步）")
    else:
        issues.extend(validate_analysis(analysis_text, material))
    if not card_path.is_file() or card_path.stat().st_size == 0:
        issues.append("未生成模式卡文件 drafts/card.yaml")
    if not diff_path.is_file() or diff_path.stat().st_size == 0:
        issues.append("未生成打法差异文件 drafts/playbook.diff.yaml")
    if diff_path.is_file() and not str(diff.get("body") or "").strip():
        issues.append("打法差异缺少 body 正文")
    if card_path.is_file() and card_path.stat().st_size > 0:
        issues.extend(validate_card(card, material))
        issues.extend(validate_body_blocking(card, body, material=material))
    end_reason = last_turn_end_reason(jsonl_text)
    if end_reason == "max-tokens" and (
        not card_path.is_file() or not diff_path.is_file() or not str(diff.get("body") or "").strip()
    ):
        issues.append("智能体达到输出长度上限，可能没来得及写完两个文件")
    return issues


def _schema_summary(issues: list[str]) -> str:
    if not issues:
        return "模式卡格式不对，结果已丢弃。"
    if issues[0].startswith("未生成"):
        return issues[0] + "，结果已丢弃。"
    return issues[0] + "，结果已丢弃。"


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _publish_session_log(dsh_home: Path, session_root: Path) -> None:
    """Copy SDK session JSONL to the path the curate audit already reads."""
    target = session_root / "session.jsonl"
    sessions = dsh_home / "sessions"
    if not sessions.is_dir():
        return
    chunks: list[str] = []
    for path in sorted(sessions.rglob("*.jsonl")):
        if path.resolve() == target.resolve():
            continue
        chunks.append(path.read_text(encoding="utf-8"))
    if chunks:
        target.write_text("".join(chunks), encoding="utf-8")


@contextmanager
def _forced_subprocess_env(env: dict[str, str]):
    real = subprocess.Popen
    forced = False

    def popen(*args, **kwargs):
        nonlocal forced
        if not forced:
            kwargs["env"] = dict(env)
            forced = True
        return real(*args, **kwargs)

    subprocess.Popen = popen
    try:
        yield
    finally:
        subprocess.Popen = real


