"""Delete publisher accounts and related publish data."""
from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from src.db.models.publishing import PublishJob, PublishLog, PublisherAccount, QrLoginSession
from src.db.models.publishing_metrics import PublishPostMetricSnapshot
from src.utils.config import Config


class AccountDeleteError(ValueError):
    """Raised when account deletion is not allowed."""


def _unlink_if_exists(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        logger.warning("Failed to remove file {}: {}", path, exc)


def _remove_tree_if_exists(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except OSError as exc:
        logger.warning("Failed to remove directory {}: {}", path, exc)


def _cleanup_account_files(
    *,
    account_id: str,
    session_path: str | None,
    browser_profile_path: str | None,
) -> None:
    root = Config.ROOT_DIR
    if session_path:
        _unlink_if_exists(root / session_path)

    profile_rel = browser_profile_path or f"data/publish/profiles/{account_id}"
    _remove_tree_if_exists(root / profile_rel)

    _unlink_if_exists(root / "data" / "publish" / "persona" / f"{account_id}.json")


def delete_publisher_account(session: Session, account_id: str) -> dict[str, int]:
    """Remove account, its jobs/logs/metrics, and on-disk session/profile files."""
    account = session.get(PublisherAccount, account_id)
    if account is None:
        raise AccountDeleteError("账号不存在")

    uploading = (
        session.query(PublishJob)
        .filter_by(account_id=account_id, status="uploading")
        .count()
    )
    if uploading:
        raise AccountDeleteError("该账号有发布任务进行中，请等待完成或取消后再删除")

    job_ids = [
        row[0]
        for row in session.query(PublishJob.id).filter_by(account_id=account_id).all()
    ]

    logs_deleted = 0
    metrics_deleted = 0
    jobs_deleted = 0
    qr_cleared = 0

    if job_ids:
        logs_deleted = (
            session.query(PublishLog)
            .filter(PublishLog.job_id.in_(job_ids))
            .delete(synchronize_session=False)
        )
        metrics_deleted = (
            session.query(PublishPostMetricSnapshot)
            .filter(PublishPostMetricSnapshot.job_id.in_(job_ids))
            .delete(synchronize_session=False)
        )
        jobs_deleted = (
            session.query(PublishJob)
            .filter_by(account_id=account_id)
            .delete(synchronize_session=False)
        )

    metrics_deleted += (
        session.query(PublishPostMetricSnapshot)
        .filter_by(account_id=account_id)
        .delete(synchronize_session=False)
    )

    qr_cleared = (
        session.query(QrLoginSession)
        .filter_by(account_id=account_id)
        .update({QrLoginSession.account_id: None}, synchronize_session=False)
    )

    session_path = account.session_path
    profile_path = account.browser_profile_path
    account_pk = account.id

    session.delete(account)
    session.commit()

    _cleanup_account_files(
        account_id=account_pk,
        session_path=session_path,
        browser_profile_path=profile_path,
    )

    return {
        "jobs_deleted": jobs_deleted,
        "logs_deleted": logs_deleted,
        "metrics_deleted": metrics_deleted,
        "qr_sessions_cleared": qr_cleared,
    }
