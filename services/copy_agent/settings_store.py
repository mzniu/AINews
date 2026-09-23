"""Current playbook pointer and the auto-publish switch."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.db.models.playbook import CopyAgentSettings, PlaybookVersion


class AutoSwitchBlocksPublish(RuntimeError):
    pass


class TrapCheckFailed(RuntimeError):
    pass


def get_settings(session: Session) -> CopyAgentSettings:
    row = session.get(CopyAgentSettings, "default")
    if row is None:
        row = CopyAgentSettings(
            id="default",
            auto_uses_current_playbook=False,
            material_adaptive_playbook=True,
            auto_material_adaptive_playbook=False,
            ranking_max_candidates=40,
        )
        session.add(row)
        session.flush()
    return row


def publish_version(session: Session, version_id: str) -> None:
    version = session.get(PlaybookVersion, version_id)
    if version is None:
        raise ValueError(f"unknown playbook version: {version_id}")
    settings = get_settings(session)
    if settings.auto_uses_current_playbook and not version.trap_passed:
        raise AutoSwitchBlocksPublish(
            "自动出片还开着，所以这一版不能换上去。先关掉「自动出片也用这一版」，就能发到主页试。试过之后再打开。"
        )
    settings.current_playbook_version_id = version.id
    version.status = "published"
    session.commit()


def set_auto_switch(session: Session, enabled: bool) -> None:
    settings = get_settings(session)
    if enabled:
        version = None
        if settings.current_playbook_version_id:
            version = session.get(PlaybookVersion, settings.current_playbook_version_id)
        if version is None or not version.trap_passed:
            raise TrapCheckFailed("陷阱检查未通过，不能打开自动出片。")
    settings.auto_uses_current_playbook = enabled
    session.commit()


def set_material_adaptive(session: Session, enabled: bool) -> None:
    settings = get_settings(session)
    settings.material_adaptive_playbook = enabled
    session.commit()


def set_auto_material_adaptive(session: Session, enabled: bool) -> None:
    settings = get_settings(session)
    settings.auto_material_adaptive_playbook = enabled
    session.commit()


def set_ranking_max_candidates(session: Session, value: int) -> None:
    if value < 5 or value > 100:
        raise ValueError("ranking_max_candidates must be between 5 and 100")
    settings = get_settings(session)
    settings.ranking_max_candidates = value
    session.commit()
