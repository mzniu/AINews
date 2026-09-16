"""Rule-based article scoring for flash-news (快讯) curation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

_CONFIG_PATH = Config.ROOT_DIR / "config" / "article_scoring.yaml"
_MONEY_METRIC_RE = re.compile(r"\d{2,}[\d,.]*\s*(亿|万|万亿|%)")
_BREAKTHROUGH_NUMBER_RE = re.compile(r"\d{2,}[\d,.]*\s*(亿|万|万亿|B|billion|M|million|%)")
_TEXT_PERCENT_RE = re.compile(r"\d{2,}%")
_TEXT_TRILLION_RE = re.compile(r"\d+(\.\d+)?\s*万亿")
_TEXT_BILLION_RE = re.compile(r"\d+(\.\d+)?\s*亿")


@dataclass
class DimensionScore:
    key: str
    label: str
    score: float
    weight: float
    weighted: float
    signals: list[str] = field(default_factory=list)


@dataclass
class ArticleScoreResult:
    profile: str
    total: float
    grade: str
    dimensions: list[DimensionScore]
    bonuses: list[dict[str, Any]]
    penalties: list[dict[str, Any]]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "total": round(self.total, 1),
            "grade": self.grade,
            "dimensions": [
                {
                    "key": d.key,
                    "label": d.label,
                    "score": round(d.score, 1),
                    "weight": d.weight,
                    "weighted": round(d.weighted, 2),
                    "signals": d.signals,
                }
                for d in self.dimensions
            ],
            "bonuses": self.bonuses,
            "penalties": self.penalties,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class _BonusCandidate:
    reason: str
    points: float


@dataclass
class _BonusBudget:
    max_points: float
    bonuses: list[dict[str, Any]]
    applied_points: float = 0.0

    @property
    def remaining_points(self) -> float:
        return max(0.0, self.max_points - self.applied_points)

    def apply(self, reason: str, requested_points: float) -> float:
        applied = min(max(0.0, requested_points), self.remaining_points)
        if applied <= 0:
            return 0.0
        self.bonuses.append({"reason": reason, "points": applied})
        self.applied_points += applied
        return applied


_DIMENSION_LABELS = {
    "timeliness": "时效性",
    "prominence": "显著性",
    "event_tension": "事件张力",
    "breakthrough": "突破性",
    "product_heat": "产品热度",
    "relevance": "话题相关",
    "data_signal": "数据信号",
    "creatability": "可创作性",
    "hot_radar": "热榜雷达",
}

DIMENSION_LABELS = _DIMENSION_LABELS

_GRADE_RECOMMENDATIONS = {
    "S": "立即出快讯",
    "A": "今日优先",
    "B": "可做简讯或合集",
    "C": "观察归档",
    "D": "不建议跟进",
}


def load_scoring_config(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    from services.ingestion.scoring_settings import load_merged_scoring_config

    return load_merged_scoring_config()


def _contains_any(text: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    lower = text.lower()
    for term in terms:
        token = term.strip()
        if not token:
            continue
        if token.lower() in lower or token in text:
            hits.append(token)
    return hits


VALID_GRADES = frozenset({"S", "A", "B", "C", "D"})
GRADE_RANK = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}


def grade_meets_minimum(grade: str | None, min_grade: str) -> bool:
    """Return True when article grade is at least min_grade (e.g. A allows S and A)."""
    current = str(grade or "").strip().upper()
    minimum = str(min_grade or "S").strip().upper()
    if current not in VALID_GRADES or minimum not in VALID_GRADES:
        return False
    return GRADE_RANK[current] >= GRADE_RANK[minimum]


def grade_from_total(total: float, cfg: dict[str, Any] | None = None) -> str:
    active = cfg or load_scoring_config()
    thresholds = active.get("grades") or {}
    if total >= float(thresholds.get("S", 88)):
        return "S"
    if total >= float(thresholds.get("A", 70)):
        return "A"
    if total >= float(thresholds.get("B", 55)):
        return "B"
    if total >= float(thresholds.get("C", 40)):
        return "C"
    return "D"


def _grade_from_total(total: float, cfg: dict[str, Any]) -> str:
    return grade_from_total(total, cfg)


def _score_timeliness(published_at: datetime | None) -> tuple[float, list[str]]:
    if published_at is None:
        return 5.0, ["发布时间未知"]
    now = datetime.utcnow()
    pub = published_at.replace(tzinfo=None) if published_at.tzinfo else published_at
    hours = max(0.0, (now - pub).total_seconds() / 3600)
    if hours <= 24:
        return 10.0, [f"约{hours:.0f}小时内"]
    if hours <= 72:
        return 8.0, [f"约{hours / 24:.1f}天内"]
    if hours <= 168:
        return 6.0, [f"约{hours / 24:.1f}天内"]
    if hours <= 720:
        return 4.0, ["超过一周"]
    return 2.0, ["时效偏弱"]


def _score_prominence(text: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    tier1 = _contains_any(text, cfg.get("tier1_companies") or [])
    celebs = _contains_any(text, cfg.get("celebrities") or [])
    tier2 = _contains_any(text, cfg.get("tier2_companies") or [])
    signals = tier1 + celebs + tier2
    if tier1 or celebs:
        return 9.0 if celebs else 8.5, signals[:6]
    if tier2:
        return 6.5, signals[:6]
    if signals:
        return 5.0, signals[:6]
    return 2.0, []


def _score_breakthrough(text: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    signals = _contains_any(text, cfg.get("breakthrough_signals") or [])
    has_big_number = bool(_BREAKTHROUGH_NUMBER_RE.search(text))
    if has_big_number and signals:
        return 9.0, (signals[:4] + ["含关键数字"])[:6]
    if signals:
        return 7.0, signals[:6]
    if has_big_number:
        return 6.0, ["含关键数字"]
    return 3.0, []


def _score_event_tension(text: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    signals = _contains_any(text, cfg.get("event_tension_signals") or [])
    tier1 = _contains_any(text, cfg.get("tier1_companies") or [])
    celebs = _contains_any(text, cfg.get("celebrities") or [])
    tier1_hits = tier1 or celebs
    high_stakes = set(cfg.get("event_tension_high_stakes") or [])
    if not signals:
        return 4.0, []
    n = len(signals)
    if n <= 2:
        score = 6.0
    elif n <= 3:
        score = 8.0
    else:
        score = 10.0 if tier1_hits else 8.0
    if tier1_hits and n >= 2:
        score = max(score, 8.0)
    if tier1_hits and high_stakes and any(signal in high_stakes for signal in signals):
        score = max(score, 8.0)
    combined = (signals + tier1 + celebs)[:6]
    return score, combined


def _score_product_heat(text: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    hits = _contains_any(text, cfg.get("hot_products") or [])
    if len(hits) >= 2:
        return 9.0, hits[:6]
    if hits:
        return 7.5, hits[:6]
    return 2.5, []


def _score_relevance(text: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    hits = _contains_any(text, cfg.get("ai_relevance_keywords") or [])
    if len(hits) >= 3:
        return 10.0, hits[:6]
    if hits:
        return 7.0 + min(2.0, len(hits)), hits[:6]
    return 3.0, []


def _score_data_signal(
    view_count: int | None,
    story_article_count: int,
    cfg: dict[str, Any],
    text: str = "",
) -> tuple[float, list[str]]:
    score = 5.0
    signals: list[str] = []
    if view_count is not None:
        if view_count >= int(cfg.get("view_count_tier2", 10000)):
            score = 9.0
            signals.append(f"浏览{view_count}")
        elif view_count >= int(cfg.get("view_count_tier1", 5000)):
            score = 7.5
            signals.append(f"浏览{view_count}")
        elif view_count > 0:
            score = 6.0
            signals.append(f"浏览{view_count}")
    if text:
        if _TEXT_TRILLION_RE.search(text):
            score = max(score, 8.0)
            signals.append("万亿级数据")
        elif _TEXT_BILLION_RE.search(text) or _MONEY_METRIC_RE.search(text):
            score = max(score, 7.0)
            signals.append("亿级/万级数据")
        elif _TEXT_PERCENT_RE.search(text):
            score = max(score, 7.0)
            signals.append("百分比数据")
    min_story = int((cfg.get("bonuses") or {}).get("multi_source_story", {}).get("min_articles", 2))
    if story_article_count >= min_story:
        score = min(10.0, score + 1.5)
        signals.append(f"同题{story_article_count}篇")
    if not signals:
        return 5.0, ["暂无外部数据"]
    return min(10.0, score), signals


def _score_creatability(
    *,
    image_count: int,
    content_len: int,
    summary: str | None,
) -> tuple[float, list[str]]:
    score = 4.0
    signals: list[str] = []
    if summary and len(summary) >= 20:
        score += 2.0
        signals.append("有摘要")
    if content_len >= 400:
        score += 2.0
        signals.append("正文充足")
    elif content_len >= 150:
        score += 1.0
    if image_count >= 3:
        score += 2.0
        signals.append(f"配图{image_count}张")
    elif image_count > 0:
        score += 1.0
        signals.append(f"配图仅{image_count}张")
    else:
        signals.append("无配图")
    return min(10.0, score), signals


def _score_hot_radar(
    match: Any | None,
    cfg: dict[str, Any],
) -> tuple[float, list[str]]:
    scoring = (cfg.get("hot_radar") or {}).get("scoring") or {}
    unmatched = float(scoring.get("unmatched", 0.0))
    if match is None:
        return unmatched, ["未命中热榜"]

    rank = int(getattr(match, "effective_rank", 0) or getattr(match, "rank", 0) or 0)
    if rank <= 3:
        score = float(scoring.get("rank_1_3", 10.0))
    elif rank <= 10:
        score = float(scoring.get("rank_4_10", 8.5))
    elif rank <= 20:
        score = float(scoring.get("rank_11_20", 7.0))
    elif rank <= 50:
        score = float(scoring.get("rank_21_50", 5.5))
    else:
        score = unmatched

    board = str(getattr(match, "board_id", "") or getattr(match, "board", "") or "ai")
    board_label = str(getattr(match, "board_name", "") or "").strip()
    board_display = str(getattr(match, "board_display", "") or "").strip()
    if board_label and board_display:
        board_text = f"{board_label}·{board_display}"
    else:
        board_text = board_label or board_display or board.upper()
    heat_label = getattr(match, "heat_label", None)
    method = str(getattr(match, "match_method", "title") or "title")
    signals = [f"{board_text}#{rank}"]
    if heat_label:
        signals.append(f"热度{heat_label}")
    signals.append("URL命中" if method == "url" else "标题命中")
    return score, signals


def _apply_industry_bonuses(
    *,
    body: str,
    dimensions: list[DimensionScore],
    bonus_cfg: dict[str, Any],
    budget: _BonusBudget,
) -> float:
    extra = 0.0
    by_key = {dimension.key: dimension for dimension in dimensions}
    prominence = by_key.get("prominence")
    event_tension = by_key.get("event_tension")
    prominence_score = prominence.score if prominence else 0.0
    event_score = event_tension.score if event_tension else 0.0

    groups: list[list[_BonusCandidate]] = [[], [], []]
    personnel, finance, technology = groups

    personnel_cfg = bonus_cfg.get("personnel_exodus") or {}
    if prominence_score >= float(personnel_cfg.get("min_prominence_score", 8.0)):
        if _contains_any(body, personnel_cfg.get("signals") or ["离职", "出走", "跳槽"]):
            personnel.append(
                _BonusCandidate("人事地震", float(personnel_cfg.get("points", 6)))
            )

    layoff_cfg = bonus_cfg.get("layoff_crisis") or {}
    if (
        prominence_score >= float(layoff_cfg.get("min_prominence_score", 8.0))
        and event_score >= float(layoff_cfg.get("min_event_tension_score", 6.0))
        and _contains_any(body, layoff_cfg.get("signals") or ["裁员", "开除", "叫停"])
    ):
        personnel.append(
            _BonusCandidate("裁员危机", float(layoff_cfg.get("points", 8)))
        )

    financial_cfg = bonus_cfg.get("financial_disclosure") or {}
    if prominence_score >= float(financial_cfg.get("min_prominence_score", 8.0)):
        if _contains_any(body, financial_cfg.get("signals") or ["收入", "营收", "被曝", "估值"]):
            finance.append(
                _BonusCandidate("财务披露", float(financial_cfg.get("points", 6)))
            )

    mega_cfg = bonus_cfg.get("mega_parameter") or {}
    if prominence_score >= float(mega_cfg.get("min_prominence_score", 8.5)):
        if _contains_any(body, mega_cfg.get("signals") or ["万亿", "万参数", "535B"]):
            technology.append(
                _BonusCandidate("超级参数", float(mega_cfg.get("points", 5)))
            )

    training_cfg = bonus_cfg.get("open_training") or {}
    breakthrough = by_key.get("breakthrough")
    if breakthrough and breakthrough.score >= float(training_cfg.get("min_breakthrough_score", 8.0)):
        training_core = training_cfg.get("core_signals") or ["直播", "训练"]
        training_open = training_cfg.get("open_signals") or ["Loss", "全公开", "开源", "公开"]
        if _contains_any(body, training_core) and _contains_any(body, training_open):
            technology.append(
                _BonusCandidate("开放训练", float(training_cfg.get("points", 8)))
            )

    executive_cfg = bonus_cfg.get("executive_voice") or {}
    if prominence_score >= float(executive_cfg.get("min_prominence_score", 8.5)):
        if _contains_any(body, executive_cfg.get("signals") or ["发声", "表态", "回应"]):
            technology.append(
                _BonusCandidate("高管发声", float(executive_cfg.get("points", 6)))
            )

    workforce_cfg = bonus_cfg.get("workforce_shock") or {}
    if (
        prominence_score >= float(workforce_cfg.get("min_prominence_score", 8.0))
        and event_score >= float(workforce_cfg.get("min_event_tension_score", 8.0))
        and _contains_any(body, workforce_cfg.get("signals") or ["裁员", "开除", "走人"])
        and (
            _TEXT_PERCENT_RE.search(body)
            or _contains_any(body, workforce_cfg.get("data_signals") or ["暴涨", "反增", "暴增"])
        )
    ):
        personnel.append(
            _BonusCandidate("用工震荡", float(workforce_cfg.get("points", 10)))
        )

    for candidates in groups:
        if candidates:
            selected = max(candidates, key=lambda candidate: candidate.points)
            extra += budget.apply(selected.reason, selected.points)

    return extra


def score_article(
    *,
    title: str,
    summary: str | None = None,
    content_text: str | None = None,
    keywords: list[str] | None = None,
    published_at: datetime | None = None,
    view_count: int | None = None,
    story_article_count: int = 1,
    image_count: int = 0,
    hot_radar_match: Any | None = None,
    config: dict[str, Any] | None = None,
) -> ArticleScoreResult:
    cfg = config or load_scoring_config()
    profile = str(cfg.get("profile") or "flash_news")
    weights: dict[str, float] = cfg.get("weights") or {}

    keyword_text = " ".join(keywords or [])
    # Relevance and topic dimensions read title + summary + keywords + body, never title alone.
    body = " ".join(filter(None, [title, summary, keyword_text, (content_text or "")[:1500]]))

    raw_dimensions = {
        "timeliness": _score_timeliness(published_at),
        "prominence": _score_prominence(body, cfg),
        "event_tension": _score_event_tension(body, cfg),
        "breakthrough": _score_breakthrough(body, cfg),
        "product_heat": _score_product_heat(body, cfg),
        "relevance": _score_relevance(body, cfg),
        "data_signal": _score_data_signal(view_count, story_article_count, cfg, body),
        "creatability": _score_creatability(
            image_count=image_count,
            content_len=len(content_text or ""),
            summary=summary,
        ),
        "hot_radar": _score_hot_radar(hot_radar_match, cfg),
    }

    dimensions: list[DimensionScore] = []
    base_total = 0.0
    for key, (score, signals) in raw_dimensions.items():
        weight = float(weights.get(key, 0.0))
        weighted = score * weight * 10
        base_total += weighted
        dimensions.append(
            DimensionScore(
                key=key,
                label=_DIMENSION_LABELS.get(key, key),
                score=score,
                weight=weight,
                weighted=weighted,
                signals=signals,
            )
        )

    bonuses: list[dict[str, Any]] = []
    penalties: list[dict[str, Any]] = []
    bonus_cfg = cfg.get("bonuses") or {}
    penalty_cfg = cfg.get("penalties") or {}
    bonus_budget = _BonusBudget(
        max_points=float((cfg.get("industry_bonus") or {}).get("max_total_points", 8)),
        bonuses=bonuses,
    )

    min_story = int(bonus_cfg.get("multi_source_story", {}).get("min_articles", 2))
    if story_article_count >= min_story:
        pts = float(bonus_cfg.get("multi_source_story", {}).get("points", 3))
        base_total += bonus_budget.apply("多源同题验证", pts)

    if view_count is not None:
        if view_count >= int(bonus_cfg.get("view_count_tier2", 10000)):
            pts = float(bonus_cfg.get("view_count_tier2_points", 4))
            base_total += bonus_budget.apply("高浏览量", pts)
        elif view_count >= int(bonus_cfg.get("view_count_tier1", 5000)):
            pts = float(bonus_cfg.get("view_count_tier1_points", 2))
            base_total += bonus_budget.apply("较高浏览量", pts)

    base_total += _apply_industry_bonuses(
        body=body,
        dimensions=dimensions,
        bonus_cfg=bonus_cfg,
        budget=bonus_budget,
    )

    hot_bonus_cfg = (cfg.get("hot_radar") or {}).get("bonuses") or {}
    if hot_radar_match is not None:
        rank = int(getattr(hot_radar_match, "effective_rank", 0) or getattr(hot_radar_match, "rank", 0) or 0)
        if rank <= 3:
            pts = float(hot_bonus_cfg.get("top3_points", 3))
            base_total += bonus_budget.apply("AI热榜Top3", pts)
        elif rank <= 10:
            pts = float(hot_bonus_cfg.get("top10_points", 1))
            base_total += bonus_budget.apply("AI热榜Top10", pts)

    marketing_hits = _contains_any(body, cfg.get("marketing_signals") or [])
    if marketing_hits and len(marketing_hits) >= 2:
        pts = float(penalty_cfg.get("marketing_only", -8))
        penalties.append({"reason": "营销稿特征", "points": pts, "signals": marketing_hits[:3]})
        base_total += pts

    insufficient_cfg = penalty_cfg.get("insufficient_images") or {}
    min_images = int(insufficient_cfg.get("min_images", 3))
    timeliness_dim = next((d for d in dimensions if d.key == "timeliness"), None)
    prominence_dim = next((d for d in dimensions if d.key == "prominence"), None)
    exempt_images = False
    exempt_cfg = insufficient_cfg.get("exempt_when") or {}
    if exempt_cfg:
        money_signal = bool(
            _MONEY_METRIC_RE.search(body)
            or _contains_any(
                body,
                ["融资", "收入", "营收", "估值", "收购", "并购", "上市", "IPO"],
            )
        )
        min_timeliness = float(exempt_cfg.get("timeliness_score_gte", 9))
        if money_signal and timeliness_dim and timeliness_dim.score >= min_timeliness:
            exempt_images = True
        breaking_signals = exempt_cfg.get("breaking_news_signals") or []
        if (
            not exempt_images
            and breaking_signals
            and timeliness_dim
            and prominence_dim
            and timeliness_dim.score
            >= float(exempt_cfg.get("breaking_news_timeliness_gte", 8.0))
            and prominence_dim.score
            >= float(exempt_cfg.get("breaking_news_prominence_gte", 8.0))
            and _contains_any(body, list(breaking_signals))
        ):
            exempt_images = True
    if image_count < min_images and not exempt_images:
        pts = float(insufficient_cfg.get("points", -6))
        penalties.append(
            {
                "reason": f"配图不足（{image_count}张，建议≥{min_images}张）",
                "points": pts,
                "signals": [f"本地配图{image_count}张"],
            }
        )
        base_total += pts

    off_topic_cfg = penalty_cfg.get("off_topic") or {}
    relevance_dim = next((d for d in dimensions if d.key == "relevance"), None)
    prominence_dim = next((d for d in dimensions if d.key == "prominence"), None)
    max_relevance = float(off_topic_cfg.get("max_relevance_score", 5))
    exempt_public_issue = bool(off_topic_cfg.get("exempt_public_issue", True))
    public_issue_hits = _contains_any(body, cfg.get("public_issue_signals") or [])
    prominence_ok = prominence_dim is not None and prominence_dim.score >= 8.5
    skip_off_topic = exempt_public_issue and prominence_ok and bool(public_issue_hits)
    if (
        relevance_dim is not None
        and relevance_dim.score < max_relevance
        and not skip_off_topic
    ):
        pts = float(off_topic_cfg.get("points", -12))
        penalties.append(
            {
                "reason": "非AI选题",
                "points": pts,
                "signals": relevance_dim.signals[:3] or ["缺少AI相关词"],
            }
        )
        base_total += pts

    total = max(0.0, min(100.0, base_total))
    grade = _grade_from_total(total, cfg)
    return ArticleScoreResult(
        profile=profile,
        total=total,
        grade=grade,
        dimensions=dimensions,
        bonuses=bonuses,
        penalties=penalties,
        recommendation=_GRADE_RECOMMENDATIONS.get(grade, "观察"),
    )
