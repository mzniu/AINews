"""Story clustering tests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.engine import Base
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionSource, Story, StoryAsset
from services.ingestion.story_cluster import (
    assign_article_to_story,
    expand_story_assets,
    merge_articles_into_story,
    normalize_title,
    score_pair,
    title_similarity,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    source = IngestionSource(
        id="aitnt_travel",
        slug="aitnt_travel",
        display_name="AITNT Travel",
        adapter_class="aitnt_news",
        config_json="{}",
    )
    db.add(source)
    db.commit()
    yield db
    db.close()


def _article(
    session,
    *,
    title: str,
    keywords: list[str] | None = None,
    published_at: datetime | None = None,
    url_suffix: str = "1",
) -> IngestedArticle:
    row = IngestedArticle(
        source_id="aitnt_travel",
        canonical_url=f"http://example.com/{url_suffix}",
        title=title,
        keywords_json=json.dumps(keywords or [], ensure_ascii=False),
        published_at=published_at or datetime.utcnow(),
        status="fetched",
    )
    session.add(row)
    session.flush()
    return row


def test_normalize_title_strips_noise():
    assert normalize_title("独家！OpenAI 刚刚发布 GPT-5") == normalize_title("OpenAI发布GPT-5")


def test_title_similarity_high_for_same_topic():
    a = "OpenAI 发布 GPT-5 多模态模型"
    b = "OpenAI发布GPT-5多模态模型详解"
    assert title_similarity(a, b) >= 0.72


def test_assign_creates_story_for_first_article(session):
    article = _article(session, title="某旅游 AI 新闻标题")
    story_id = assign_article_to_story(session, article)
    session.commit()
    assert story_id
    assert session.query(Story).count() == 1
    assert article.story_id == story_id


def test_assign_links_similar_articles(session):
    now = datetime.utcnow()
    first = _article(
        session,
        title="OpenAI 发布 GPT-5 旅游行业应用",
        keywords=["OpenAI", "GPT-5", "旅游"],
        published_at=now - timedelta(hours=1),
        url_suffix="a",
    )
    assign_article_to_story(session, first)
    session.commit()

    second = _article(
        session,
        title="OpenAI发布GPT-5旅游行业应用详解",
        keywords=["OpenAI", "GPT-5", "旅游"],
        published_at=now,
        url_suffix="b",
    )
    story_id = assign_article_to_story(session, second)
    session.commit()

    assert story_id == first.story_id
    assert session.query(Story).count() == 1


def test_expand_story_assets_dedupes_images(session):
    a1 = _article(session, title="主文", url_suffix="x")
    a2 = _article(session, title="相关文", url_suffix="y")
    story_id = merge_articles_into_story(session, [a1.id, a2.id])
    session.add(
        ArticleImage(
            article_id=a1.id,
            original_url="http://img/1.jpg",
            local_path="data/a/1.jpg",
            download_status="ok",
            sort_order=1,
        )
    )
    session.add(
        ArticleImage(
            article_id=a2.id,
            original_url="http://img/1.jpg",
            local_path="data/a/1.jpg",
            download_status="ok",
            sort_order=1,
        )
    )
    session.add(
        ArticleImage(
            article_id=a2.id,
            original_url="http://img/2.jpg",
            local_path="data/a/2.jpg",
            download_status="ok",
            sort_order=2,
        )
    )
    session.commit()
    count = expand_story_assets(session, story_id)
    session.commit()
    assert count == 2
    assert session.query(StoryAsset).filter_by(story_id=story_id).count() == 2


def test_score_pair_prefers_matching_theme(session):
    left = _article(
        session,
        title="AI 旅游助手 TripMind 正式上线",
        keywords=["AI", "旅游"],
        url_suffix="l",
    )
    left.theme = "旅游"
    right = _article(
        session,
        title="AI旅游助手TripMind正式上线",
        keywords=["AI", "旅游"],
        url_suffix="r",
    )
    right.theme = "旅游"
    assert score_pair(left, right) >= 0.72
