"""Tests for single-article cover retry."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.ingestion.cover_retry import render_cover_for_article
from src.db.engine import Base
from src.db.models.ingestion import (
    ArticleImage,
    ImageRelevanceEvaluation,
    IngestedArticle,
    IngestionSource,
)


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "cover_retry.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "static" / "imgs").mkdir(parents=True)
    (tmp_path / "static" / "imgs" / "bg.png").write_bytes(b"")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        IngestionSource(
            id="src1",
            slug="test",
            display_name="Test",
            adapter_class="test",
            enabled=True,
        )
    )
    img_path = tmp_path / "cover_src.jpg"
    Image.new("RGB", (1080, 1440), color="blue").save(img_path)
    session.add(
        IngestedArticle(
            id="art1",
            source_id="src1",
            canonical_url="https://example.com/a1",
            title="测试封面重做",
            video_draft_json=json.dumps({"main_line1": "主标题", "sub_title": "副标题"}),
        )
    )
    session.add(
        ArticleImage(
            id="img1",
            article_id="art1",
            original_url="https://cdn.example.com/a.jpg",
            local_path=str(img_path),
            download_status="ok",
            sort_order=0,
        )
    )
    session.add(
        ImageRelevanceEvaluation(
            article_id="art1",
            source_type="article_image",
            source_id="img1",
            original_url="https://cdn.example.com/a.jpg",
            local_path=str(img_path),
            relevance_score=90,
            relevance_grade="A",
            relevance_rank=1,
            breakdown_json=json.dumps({"dimensions": {"cover_fit": {"score": 95}}}),
        )
    )
    session.commit()
    yield session
    session.close()


def test_render_cover_for_article_success(db_session, tmp_path, monkeypatch):
    from src.utils.config import Config

    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    mock_render = MagicMock(
        return_value={"success": True, "cover_path": "data/publish/covers/art1_cover.jpg"},
    )
    mock_module = MagicMock(render_article_cover=mock_render)
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "services.ingestion.cover_render_service", mock_module)
        result = render_cover_for_article(db_session, "art1")
    assert result["success"] is True
    assert result["cover_path"] == "data/publish/covers/art1_cover.jpg"
    row = db_session.get(IngestedArticle, "art1")
    assert row.generated_cover_path == "data/publish/covers/art1_cover.jpg"


def test_render_cover_for_article_no_candidate(db_session):
    db_session.query(ImageRelevanceEvaluation).delete()
    db_session.commit()
    result = render_cover_for_article(db_session, "art1")
    assert result["success"] is False
    assert result["error"] == "no_scored_cover_image"
