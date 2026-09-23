"""Aggregate publish jobs with the latest metric snapshot inside 72 hours."""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy.orm import Session

from services.copy_agent.pattern_library import pattern_rollups_from_rows
from services.copy_agent.versions import labels_for_playbook_versions
from src.db.models.playbook import CopyDraft
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models.publishing_metrics import PublishPostMetricSnapshot

_NO_LIKE = "无赞，未算比率"


def build_battle_report(session: Session) -> dict:
    jobs = session.query(PublishJob).order_by(PublishJob.created_at.asc(), PublishJob.id.asc()).all()
    account_ids = {job.account_id for job in jobs}
    accounts = {}
    if account_ids:
        accounts = {
            row.id: row
            for row in session.query(PublisherAccount).filter(PublisherAccount.id.in_(account_ids)).all()
        }
    version_ids = {job.playbook_version_id for job in jobs if job.playbook_version_id}
    version_labels = labels_for_playbook_versions(session, version_ids)
    rows = [_row(session, job, accounts.get(job.account_id), version_labels) for job in jobs]
    learn_again = [row for row in rows if row["attribution"] == "playbook"]
    return {
        "rows": rows,
        "learn_again": learn_again,
        "pattern_rollups": pattern_rollups_from_rows(learn_again),
        "selection_fallback_count": _selection_fallback_count(session),
    }


def _selection_fallback_count(session: Session) -> int:
    count = 0
    for draft in session.query(CopyDraft).all():
        try:
            sel = json.loads(draft.selection_json or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(sel, dict) and sel.get("fallback"):
            count += 1
    return count


def _row(
    session: Session,
    job: PublishJob,
    account: PublisherAccount | None,
    version_labels: dict[str, dict],
) -> dict:
    snap = _snapshot_within_72h(session, job)
    platform = ""
    if snap is not None and snap.platform:
        platform = snap.platform
    elif account is not None:
        platform = account.platform
    share = snap.share_count if snap is not None else None
    like = snap.like_count if snap is not None else None
    if like is None or like == 0:
        ratio = None
        note = _NO_LIKE
    else:
        ratio = (share or 0) / like
        note = None
    meta = version_labels.get(job.playbook_version_id or "", {})
    return {
        "job_id": job.id,
        "attribution": job.playbook_attribution,
        "playbook_version_id": job.playbook_version_id,
        "pattern_name": meta.get("pattern_name") or "",
        "motives_primary_label": meta.get("motives_primary_label") or "",
        "verdict_function_label": meta.get("verdict_function_label") or "",
        "platform": platform,
        "share_count": share,
        "like_count": like,
        "ratio": ratio,
        "ratio_note": note,
    }


def _snapshot_within_72h(session: Session, job: PublishJob) -> PublishPostMetricSnapshot | None:
    if job.published_at is None:
        return None
    deadline = job.published_at + timedelta(hours=72)
    return (
        session.query(PublishPostMetricSnapshot)
        .filter(
            PublishPostMetricSnapshot.job_id == job.id,
            PublishPostMetricSnapshot.fetched_at <= deadline,
        )
        .order_by(PublishPostMetricSnapshot.fetched_at.desc())
        .first()
    )
