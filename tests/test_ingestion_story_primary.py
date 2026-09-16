"""Story primary election and media pipeline gate tests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.ingestion.media_job_service import maybe_enqueue_media_job
from services.ingestion.story_cluster import assign_article_to_story
from services.ingestion.story_primary import (
    elect_primary_article,
    refresh_story_primary,
)
from src.db.engine import Base
from src.db.models.ingestion import IngestedArticle, IngestionSource, Story, StoryArticle


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="aitnt_news",
            config_json="{}",
        )
    )
    db.commit()
    yield db
    db.close()


def _article(
    session,
    *,
    title: str,
    score_total: float | None = None,
    created_at: datetime | None = None,
    url_suffix: str = "1",
) -> IngestedArticle:
    row = IngestedArticle(
        source_id="src1",
        canonical_url=f"http://example.com/{url_suffix}",
        title=title,
        content_text=f"{title} body",
        published_at=datetime.utcnow(),
        status="fetched",
        score_total=score_total,
        created_at=created_at or datetime.utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def test_elect_primary_prefers_higher_score(session):
    older = _article(session, title="older", score_total=70.0, url_suffix="a")
    newer = _article(session, title="newer", score_total=88.0, url_suffix="b")
    assert elect_primary_article([older, newer]).id == newer.id


def test_elect_primary_tie_breaks_on_created_at(session):
    first = _article(
        session,
        title="first",
        score_total=80.0,
        created_at=datetime.utcnow() - timedelta(hours=2),
        url_suffix="a",
    )
    second = _article(
        session,
        title="second",
        score_total=80.0,
        created_at=datetime.utcnow() - timedelta(hours=1),
        url_suffix="b",
    )
    assert elect_primary_article([first, second]).id == first.id


def test_refresh_story_primary_updates_story_and_roles(session):
    first = _article(session, title="OpenAI GPT-5", score_total=75.0, url_suffix="a")
    second = _article(session, title="OpenAI GPT-5 详解", score_total=90.0, url_suffix="b")
    assign_article_to_story(session, first)
    assign_article_to_story(session, second)
    session.commit()

    story = session.get(Story, first.story_id)
    assert story is not None
    assert story.primary_article_id == second.id
    links = session.query(StoryArticle).filter_by(story_id=story.id).all()
    roles = {link.article_id: link.role for link in links}
    assert roles[second.id] == "primary"
    assert roles[first.id] == "related"


def test_maybe_enqueue_skips_non_primary_article(session):
    low = _article(session, title="OpenAI GPT-5", score_total=88.0, url_suffix="a")
    high = _article(session, title="OpenAI GPT-5 详解", score_total=92.0, url_suffix="b")
    assign_article_to_story(session, low)
    assign_article_to_story(session, high)
    refresh_story_primary(session, low.story_id)
    session.commit()

    result = maybe_enqueue_media_job(session, low, final_grade="S", final_total=88.0)
    assert result.get("skipped") is True
    assert result.get("reason") == "not_story_primary"


def test_maybe_enqueue_skips_when_sibling_pipeline_succeeded(session):
    sibling = _article(session, title="OpenAI GPT-5", score_total=85.0, url_suffix="a")
    primary = _article(session, title="OpenAI GPT-5 详解", score_total=90.0, url_suffix="b")
    assign_article_to_story(session, sibling)
    assign_article_to_story(session, primary)
    refresh_story_primary(session, sibling.story_id)
    sibling.media_pipeline_status = "succeeded"
    sibling.generated_video_path = "data/video.mp4"
    session.commit()

    result = maybe_enqueue_media_job(session, primary, final_grade="S", final_total=90.0)
    assert result.get("skipped") is True
    assert result.get("reason") == "story_pipeline_active_or_done"
