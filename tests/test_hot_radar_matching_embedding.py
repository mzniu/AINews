"""Tests for embedding gray-zone title matching (phase 3)."""
from __future__ import annotations

from services.ingestion.hot_radar_matching import score_title_pair_with_embedding


def test_embedding_resolves_gray_zone_titles(monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.hot_radar_matching.text_embedding_similarity",
        lambda left_text, right_text, config=None: 0.82,
    )
    monkeypatch.setattr(
        "services.ingestion.hot_radar_matching.title_similarity",
        lambda left, right: 0.65,
    )
    cfg = {
        "title_similarity_threshold": 0.72,
        "gray_zone_low": 0.55,
        "gray_zone_high": 0.72,
        "use_embedding_in_gray": True,
        "embedding_threshold": 0.78,
        "embedding": {"dimensions": 256},
    }
    conf, method = score_title_pair_with_embedding(
        "title alpha",
        "title beta",
        entity_names=[],
        config=cfg,
    )
    assert method == "title_embedding"
    assert conf >= 0.78
