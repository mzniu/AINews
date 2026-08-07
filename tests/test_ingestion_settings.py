"""Tests for ingestion settings merge."""
from services.ingestion.settings import (
    build_local_from_public,
    merge_ingestion_config,
    public_ingestion_settings,
    save_ingestion_local,
)


def test_merge_local_overrides_source_fields(tmp_path, monkeypatch):
    from services.ingestion import settings as mod

    base_path = tmp_path / "ingestion_sources.yaml"
    local_path = tmp_path / "ingestion.local.yaml"
    base_path.write_text(
        """
version: 1
defaults:
  request_delay_sec: 2
sources:
  - id: kr36_ai
    display_name: 36氪
    enabled: true
    schedule_cron: "0 * * * *"
    max_list_pages: 2
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "INGESTION_BASE_PATH", base_path)
    monkeypatch.setattr(mod, "INGESTION_LOCAL_PATH", local_path)

    save_ingestion_local(
        {
            "version": 1,
            "worker": {"poll_interval_sec": 8},
            "defaults": {"request_delay_sec": 3},
            "sources": {"kr36_ai": {"max_list_pages": 1, "schedule_cron": "15 * * * *"}},
        }
    )

    merged = mod.load_merged_ingestion_config()
    src = merged["sources"][0]
    assert merged["defaults"]["request_delay_sec"] == 3
    assert merged["worker"]["poll_interval_sec"] == 8
    assert src["max_list_pages"] == 1
    assert src["schedule_cron"] == "15 * * * *"


def test_build_local_from_public_roundtrip(tmp_path, monkeypatch):
    from services.ingestion import settings as mod

    base_path = tmp_path / "ingestion_sources.yaml"
    local_path = tmp_path / "ingestion.local.yaml"
    base_path.write_text(
        """
version: 1
defaults:
  request_delay_sec: 2
sources:
  - id: a
    display_name: A
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "INGESTION_BASE_PATH", base_path)
    monkeypatch.setattr(mod, "INGESTION_LOCAL_PATH", local_path)

    payload = {
        "version": 1,
        "worker": {"poll_interval_sec": 6},
        "defaults": {"request_delay_sec": 4},
        "sources": [{"id": "a", "display_name": "A", "enabled": False, "schedule_cron": "5 * * * *"}],
    }
    save_ingestion_local(build_local_from_public(payload))
    public = public_ingestion_settings()
    assert public["defaults"]["request_delay_sec"] == 4
    assert public["sources"][0]["enabled"] is False
