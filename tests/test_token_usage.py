"""Tests for LLM/VL token usage recording and aggregation."""
from types import SimpleNamespace

from src.db.engine import init_db, get_session_factory
from services.model_config.token_usage import (
    parse_completion_usage,
    record_token_usage,
    query_token_usage,
    clear_token_usage,
    complete_chat,
)


def test_parse_usage_reads_openai_shape():
    resp = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14)
    )
    assert parse_completion_usage(resp) == (10, 4, 14)


def test_parse_usage_missing_is_zero():
    assert parse_completion_usage(SimpleNamespace()) == (0, 0, 0)
    assert parse_completion_usage(SimpleNamespace(usage=SimpleNamespace())) == (0, 0, 0)


def test_parse_usage_fills_total_from_parts():
    resp = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2))
    assert parse_completion_usage(resp) == (3, 2, 5)


def test_query_usage_aggregates_by_model_and_task(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    with factory() as session:
        record_token_usage(
            kind="language",
            profile_id="p1",
            provider="deepseek",
            model="deepseek-chat",
            task="content_gen",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            session=session,
        )
        record_token_usage(
            kind="vision",
            profile_id="v1",
            provider="qwen",
            model="qwen-vl-max",
            task="image_score",
            prompt_tokens=800,
            completion_tokens=50,
            total_tokens=850,
            session=session,
        )
        session.commit()
        summary = query_token_usage(session, range_key="all")
    assert summary["totals"]["calls"] == 2
    assert summary["totals"]["total_tokens"] == 970
    assert summary["totals"]["language_tokens"] == 120
    assert summary["totals"]["vision_tokens"] == 850
    models = {row["model"]: row for row in summary["by_model"]}
    assert models["deepseek-chat"]["calls"] == 1
    tasks = {row["task"]: row for row in summary["by_task"]}
    assert tasks["image_score"]["total_tokens"] == 850
    assert tasks["image_score"]["label"] == "配图评分"


def test_clear_token_usage(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    with factory() as session:
        record_token_usage(
            kind="language",
            profile_id="p1",
            provider="deepseek",
            model="deepseek-chat",
            task="model_test",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            session=session,
        )
        session.commit()
        deleted = clear_token_usage(session)
        session.commit()
        summary = query_token_usage(session, range_key="all")
    assert deleted == 1
    assert summary["totals"]["calls"] == 0


def test_query_usage_rejects_bad_range(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    with factory() as session:
        try:
            query_token_usage(session, range_key="yesterday")
            raised = False
        except ValueError as exc:
            raised = True
            assert "invalid range" in str(exc).lower()
    assert raised


def test_complete_chat_records_usage(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()

    class _Completions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=9, completion_tokens=1, total_tokens=10),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    resp = complete_chat(
        client,
        kind="language",
        profile={"id": "p1", "provider": "deepseek", "model": "deepseek-chat"},
        task="model_test",
        model="deepseek-chat",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert resp.choices[0].message.content == "ok"
    factory = get_session_factory()
    with factory() as session:
        summary = query_token_usage(session, range_key="all")
    assert summary["totals"]["total_tokens"] == 10
    assert summary["totals"]["calls"] == 1
