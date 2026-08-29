"""Tests for matching published jobs to platform metrics rows."""
from datetime import datetime, timedelta

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.post_matcher import (
    MATCH_FUZZY,
    MATCH_EXACT,
    MATCH_UNMATCHED,
    match_jobs_to_metrics,
    normalize_title,
    titles_fuzzy_match,
)


def _job(job_id: str, title: str, post_id: str | None, published_at: datetime):
    return {
        "id": job_id,
        "title": title,
        "platform_post_id": post_id,
        "published_at": published_at,
    }


def test_normalize_title_strips_whitespace_and_case():
    assert normalize_title("  Hello World  ") == "helloworld"


def test_match_by_platform_post_id():
    published_at = datetime(2026, 8, 10, 12, 0, 0)
    jobs = [_job("j1", "标题A", "note123", published_at)]
    items = [
        PostMetricsItem(
            platform_post_id="note123",
            title="标题A",
            published_at=published_at,
            view_count=100,
        )
    ]
    result = match_jobs_to_metrics(jobs, items)
    assert result["j1"].status == MATCH_EXACT
    assert result["j1"].metrics.view_count == 100


def test_fuzzy_match_by_title_and_time_window():
    published_at = datetime(2026, 8, 10, 12, 0, 0)
    jobs = [_job("j1", "AI 新闻速递", "xhs_999", published_at)]
    items = [
        PostMetricsItem(
            platform_post_id="real-note-1",
            title="AI新闻速递",
            published_at=published_at + timedelta(hours=2),
            view_count=50,
            like_count=3,
        )
    ]
    result = match_jobs_to_metrics(jobs, items, fuzzy_hours=24)
    assert result["j1"].status == MATCH_FUZZY
    assert result["j1"].metrics.platform_post_id == "real-note-1"


def test_unmatched_when_no_candidate():
    published_at = datetime(2026, 8, 10, 12, 0, 0)
    jobs = [_job("j1", "完全不同", "xhs_1", published_at)]
    items = [
        PostMetricsItem(
            platform_post_id="other",
            title="另一篇",
            published_at=published_at,
            view_count=1,
        )
    ]
    result = match_jobs_to_metrics(jobs, items)
    assert result["j1"].status == MATCH_UNMATCHED
    assert result["j1"].metrics is None


def test_fuzzy_match_when_platform_returns_long_caption():
    published_at = datetime(2026, 8, 10, 14, 55, 5)
    jobs = [_job("j1", "网友：挖人不成，反被灌满额度", "ks_1786373705", published_at)]
    items = [
        PostMetricsItem(
            platform_post_id="3xzci9adbqicz8u",
            title="\n网友：挖人不成，反被灌满额度\n抢用户的下一战，不在模型在工具\n#AI编程",
            published_at=published_at + timedelta(minutes=2),
            view_count=33,
        )
    ]
    assert titles_fuzzy_match(jobs[0]["title"], items[0].title)
    result = match_jobs_to_metrics(jobs, items, fuzzy_hours=24)
    assert result["j1"].status == MATCH_FUZZY


def test_time_sequence_match_for_synthetic_ids():
    base = datetime(2026, 8, 10, 14, 55, 5)
    jobs = [
        _job("j1", "短标题A", "ks_1", base),
        _job("j2", "短标题B", "ks_2", base - timedelta(hours=8)),
    ]
    items = [
        PostMetricsItem(
            platform_post_id="work-1",
            title="平台完整文案A",
            published_at=base + timedelta(seconds=12),
            view_count=10,
        ),
        PostMetricsItem(
            platform_post_id="work-2",
            title="平台完整文案B",
            published_at=base - timedelta(hours=8) + timedelta(seconds=12),
            view_count=20,
        ),
    ]
    result = match_jobs_to_metrics(jobs, items)
    assert result["j1"].status == MATCH_FUZZY
    assert result["j1"].metrics.platform_post_id == "work-1"
    assert result["j2"].metrics.platform_post_id == "work-2"


def test_time_sequence_match_for_douyin_synthetic_ids():
    base = datetime(2026, 8, 10, 14, 58, 37)
    jobs = [_job("j1", "短标题", "dy_1786373917", base)]
    items = [
        PostMetricsItem(
            platform_post_id="7123456789012345678",
            title="平台长文案",
            published_at=base + timedelta(seconds=20),
            view_count=100,
        )
    ]
    result = match_jobs_to_metrics(jobs, items)
    assert result["j1"].status == MATCH_FUZZY
    assert result["j1"].metrics.platform_post_id == "7123456789012345678"


def test_match_by_platform_post_url_when_id_is_synthetic():
    published_at = datetime(2026, 8, 10, 12, 0, 0)
    jobs = [
        {
            "id": "j1",
            "title": "本地短标题",
            "platform_post_id": "xhs_999",
            "platform_post_url": "https://www.xiaohongshu.com/explore/note123",
            "published_at": published_at,
        }
    ]
    items = [
        PostMetricsItem(
            platform_post_id="note123",
            title="平台完全不同的标题",
            published_at=published_at,
            view_count=88,
        )
    ]
    result = match_jobs_to_metrics(jobs, items, platform="xiaohongshu")
    assert result["j1"].status == MATCH_EXACT
    assert result["j1"].metrics.view_count == 88


def test_time_sequence_match_for_wechat_synthetic_ids():
    base = datetime(2026, 8, 10, 15, 3, 13)
    jobs = [_job("j1", "短标题", "wx_1786374193", base)]
    items = [
        PostMetricsItem(
            platform_post_id="export/UzFfBgAAtest",
            title="平台长文案",
            published_at=base + timedelta(seconds=20),
            view_count=542,
        )
    ]
    result = match_jobs_to_metrics(jobs, items)
    assert result["j1"].status == MATCH_FUZZY
