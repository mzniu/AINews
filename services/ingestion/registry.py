"""Adapter registry and YAML loader."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Type

import yaml

from services.ingestion.adapters.aitnt_news import AitntNewsAdapter
from services.ingestion.adapters.kr36_news import Kr36NewsAdapter
from services.ingestion.adapters.leiphone_news import LeiphoneNewsAdapter
from services.ingestion.adapters.qbitai_news import QbitaiNewsAdapter
from src.db.models.ingestion import IngestionSource
from src.utils.config import Config

ADAPTER_CLASSES: Dict[str, Type] = {
    "aitnt_news": AitntNewsAdapter,
    "kr36_news": Kr36NewsAdapter,
    "leiphone_news": LeiphoneNewsAdapter,
    "qbitai_news": QbitaiNewsAdapter,
}

INGESTION_CONFIG_PATH = Config.ROOT_DIR / "config" / "ingestion_sources.yaml"


def load_ingestion_yaml() -> dict:
    from services.ingestion.settings import load_merged_ingestion_config

    return load_merged_ingestion_config()


def merge_source_config(source: dict, defaults: dict) -> dict:
    merged = {**defaults, **source}
    return merged


def sync_sources_to_db(session) -> list[IngestionSource]:
    data = load_ingestion_yaml()
    defaults = data.get("defaults") or {}
    results: list[IngestionSource] = []
    for raw in data.get("sources") or []:
        cfg = merge_source_config(raw, defaults)
        source_id = cfg["id"]
        row = session.get(IngestionSource, source_id)
        if row is None:
            row = IngestionSource(
                id=source_id,
                slug=cfg.get("slug", source_id),
                display_name=cfg.get("display_name", source_id),
                adapter_class=cfg.get("adapter", "aitnt_news"),
            )
            session.add(row)
        row.slug = cfg.get("slug", source_id)
        row.display_name = cfg.get("display_name", source_id)
        row.adapter_class = cfg.get("adapter", "aitnt_news")
        row.enabled = bool(cfg.get("enabled", True))
        row.schedule_cron = cfg.get("schedule_cron") or defaults.get("schedule_cron", "0 * * * *")
        row.config_json = json.dumps(cfg, ensure_ascii=False)
        results.append(row)
    session.commit()
    return results


def build_adapter(source: IngestionSource):
    cfg = json.loads(source.config_json or "{}")
    adapter_name = source.adapter_class
    cls = ADAPTER_CLASSES.get(adapter_name)
    if cls is None:
        raise ValueError(f"Unknown adapter: {adapter_name}")
    return cls(
        source_id=source.id,
        base_url=cfg.get("base_url", ""),
    )


def get_source_config(source: IngestionSource) -> dict[str, Any]:
    return json.loads(source.config_json or "{}")
