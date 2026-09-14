"""Viral potential scoring — shareability separate from industry quality."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.ingestion.article_scorer import (
    _contains_any,
    grade_from_total,
    load_scoring_config,
)

_MONEY_YI_RE = re.compile(r"\d+(\.\d+)?\s*亿")
_MONEY_WAN_HIGH_RE = re.compile(r"\d{4,}(\.\d+)?\s*万")  # 1000万+
_MONEY_WAN_RE = re.compile(r"\d{3,}(\.\d+)?\s*万")
_MONEY_WAN_TRILLION_RE = re.compile(r"\d+(\.\d+)?\s*万亿")
_NUMBER_RE = re.compile(r"\d+[\d,.]*%?")

MOTIVE_LABELS = {
    "social_currency": "社交货币",
    "emotional_arousal": "情绪唤醒",
    "identity": "身份认同",
    "public_issue": "公共议题",
}

VIRAL_GRADE_RECOMMENDATIONS = {
    "S": "高传播潜力",
    "A": "较强传播潜力",
    "B": "一般传播潜力",
    "C": "偏弱传播潜力",
    "D": "低传播潜力",
}


@dataclass
class HookGateResult:
    passed: bool
    subject: bool
    number: bool
    conflict: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "subject": self.subject,
            "number": self.number,
            "conflict": self.conflict,
        }


@dataclass
class MotiveScore:
    key: str
    label: str
    score: float
    weight: float
    weighted: float
    signals: list[str] = field(default_factory=list)


@dataclass
class ViralScoreResult:
    total: float
    grade: str
    motives: list[MotiveScore]
    hook_gate: HookGateResult
    bonuses: list[dict[str, Any]]
    platform_fit: list[str]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 1),
            "grade": self.grade,
            "motives": [
                {
                    "key": m.key,
                    "label": m.label,
                    "score": round(m.score, 1),
                    "weight": m.weight,
                    "weighted": round(m.weighted, 2),
                    "signals": m.signals,
                }
                for m in self.motives
            ],
            "hook_gate": self.hook_gate.to_dict(),
            "bonuses": self.bonuses,
            "platform_fit": self.platform_fit,
            "recommendation": self.recommendation,
        }


def load_viral_scoring_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    active = cfg or load_scoring_config()
    viral = active.get("viral_scoring") or {}
    if not viral:
        return _default_viral_config()
    return viral


def _default_viral_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "grades": {"S": 75, "A": 60, "B": 45, "C": 30},
        "hook_gate": {"min_dimensions": 2},
        "motives": {
            "social_currency": {
                "weight": 0.30,
                "shock_words": ["暴涨", "暴跌", "翻倍", "10倍"],
            },
            "emotional_arousal": {
                "weight": 0.25,
                "signals": ["离职", "裁员", "开除", "叫停", "翻车", "对峙", "决裂", "内斗"],
            },
            "identity": {
                "weight": 0.25,
                "signals": ["00后", "博士", "红娘", "天才", "少年", "创业", "退款", "结婚"],
            },
            "public_issue": {
                "weight": 0.20,
                "signals": ["CEO", "卸任", "接任", "监管", "禁令", "制裁"],
                "require_tier1": True,
            },
        },
        "bonuses": {
            "hot_radar_entry": {"max_rank": 20, "points": 10},
            "multi_source": {"min_articles": 2, "points": 6},
            "all_motives_present": {"min_score": 5.0, "points": 8},
            "money_shock": {"min_social_score": 8.0, "points": 20},
            "personnel_conflict": {
                "min_emotional_score": 6.0,
                "min_prominence_score": 8.0,
                "points": 12,
            },
            "identity_highlight": {"min_identity_score": 6.0, "points": 8},
        },
        "platform_fit": {
            "wechat_channels": ["emotional_arousal", "public_issue", "identity"],
            "douyin": ["social_currency", "emotional_arousal"],
            "kuaishou": ["identity", "social_currency"],
        },
    }


def _grade_from_viral_total(total: float, cfg: dict[str, Any]) -> str:
    thresholds = cfg.get("grades") or {"S": 75, "A": 60, "B": 45, "C": 30}
    wrapped = {"grades": thresholds}
    return grade_from_total(total, wrapped)


def _has_tier1_subject(text: str, cfg: dict[str, Any], prominence_score: float) -> bool:
    if prominence_score >= 8.0:
        return True
    tier1 = _contains_any(text, cfg.get("tier1_companies") or [])
    celebs = _contains_any(text, cfg.get("celebrities") or [])
    return bool(tier1 or celebs)


def evaluate_hook_gate(
    *,
    title: str,
    summary: str,
    cfg: dict[str, Any] | None = None,
    prominence_score: float = 0.0,
) -> HookGateResult:
    active_cfg = cfg or load_scoring_config()
    viral_cfg = load_viral_scoring_config(active_cfg)
    gate_cfg = viral_cfg.get("hook_gate") or {}
    min_dims = int(gate_cfg.get("min_dimensions", 2))

    text = f"{title} {summary}"
    subject = _has_tier1_subject(text, active_cfg, prominence_score)
    numbers = _NUMBER_RE.findall(title or "")
    number = len(numbers) > 0 and any(len(re.sub(r"\D", "", n)) >= 2 for n in numbers)

    conflict_words = (
        (viral_cfg.get("motives") or {}).get("emotional_arousal", {}).get("signals")
        or ["离职", "裁员", "叫停", "翻车", "对峙", "决裂"]
    )
    hook_patterns = active_cfg.get("hook_patterns") or []
    conflict_hits = _contains_any(text, list(conflict_words) + list(hook_patterns))
    conflict = bool(conflict_hits)

    hits = sum([subject, number, conflict])
    return HookGateResult(
        passed=hits >= min_dims,
        subject=subject,
        number=number,
        conflict=conflict,
    )


def _score_social_currency(text: str, title: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    motive_cfg = (cfg.get("motives") or {}).get("social_currency") or {}
    signals: list[str] = []
    score = 2.0
    if _MONEY_WAN_TRILLION_RE.search(text):
        score = 10.0
        signals.append("万亿级数字")
    elif _MONEY_YI_RE.search(text):
        score = 8.0
        signals.append("亿级数字")
    elif _MONEY_WAN_HIGH_RE.search(text):
        score = 8.0
        signals.append("千万级数字")
    elif _MONEY_WAN_RE.search(text):
        score = 6.0
        signals.append("万级数字")
    shock_hits = _contains_any(text, motive_cfg.get("shock_words") or [])
    if shock_hits:
        score = min(10.0, score + 1.5)
        signals.extend(shock_hits[:2])
    if _NUMBER_RE.findall(title) and score < 6.0:
        score = 6.0
        signals.append("标题含数字")
    return min(10.0, score), signals[:6]


def _score_motive_from_signals(
    text: str,
    motive_key: str,
    cfg: dict[str, Any],
    *,
    require_tier1: bool = False,
    prominence_score: float = 0.0,
    root_cfg: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    motive_cfg = (cfg.get("motives") or {}).get(motive_key) or {}
    signals = _contains_any(text, motive_cfg.get("signals") or [])
    if require_tier1 and motive_cfg.get("require_tier1", False):
        if not _has_tier1_subject(text, root_cfg or {}, prominence_score):
            return 2.0, []
    if not signals:
        return 2.0, []
    if len(signals) >= 3:
        return 9.0, signals[:6]
    if len(signals) >= 2:
        return 7.5, signals[:6]
    return 6.0, signals[:6]


def _apply_combo_bonuses(
    *,
    body: str,
    motives: list[MotiveScore],
    prominence_score: float,
    bonuses: list[dict[str, Any]],
    bonus_cfg: dict[str, Any],
) -> float:
    extra = 0.0
    by_key = {m.key: m for m in motives}

    layoff_cfg = bonus_cfg.get("layoff_shock") or {}
    if _contains_any(body, layoff_cfg.get("signals") or ["裁员", "开除", "走人"]):
        emo = by_key.get("emotional_arousal")
        if (
            emo
            and emo.score >= float(layoff_cfg.get("min_emotional_score", 7.0))
            and prominence_score >= float(layoff_cfg.get("min_prominence_score", 8.0))
        ):
            pts = float(layoff_cfg.get("points", 18))
            bonuses.append({"reason": "裁员震荡", "points": pts})
            extra += pts

    fin_cfg = bonus_cfg.get("financial_exposure") or {}
    social = by_key.get("social_currency")
    if social and social.score >= float(fin_cfg.get("min_social_score", 8.0)):
        if _contains_any(body, fin_cfg.get("signals") or ["收入", "营收", "被曝", "估值"]):
            pts = float(fin_cfg.get("points", 12))
            bonuses.append({"reason": "财务曝光", "points": pts})
            extra += pts

    consumer_cfg = bonus_cfg.get("consumer_story") or {}
    identity = by_key.get("identity")
    if (
        identity
        and identity.score >= float(consumer_cfg.get("min_identity_score", 8.0))
        and social
        and social.score >= float(consumer_cfg.get("min_social_score", 6.0))
    ):
        pts = float(consumer_cfg.get("points", 12))
        bonuses.append({"reason": "民生故事", "points": pts})
        extra += pts

    ceo_cfg = bonus_cfg.get("ceo_vision") or {}
    public_issue = by_key.get("public_issue")
    if (
        public_issue
        and public_issue.score >= float(ceo_cfg.get("min_public_issue_score", 6.0))
        and social
        and social.score >= float(ceo_cfg.get("min_social_score", 8.0))
    ):
        pts = float(ceo_cfg.get("points", 10))
        bonuses.append({"reason": "CEO战略", "points": pts})
        extra += pts

    scale_cfg = bonus_cfg.get("tier1_scale") or {}
    if prominence_score >= float(scale_cfg.get("min_prominence_score", 8.5)):
        if _contains_any(body, scale_cfg.get("signals") or ["万亿", "亿人", "万参数"]):
            pts = float(scale_cfg.get("points", 8))
            bonuses.append({"reason": "超级规模", "points": pts})
            extra += pts

    return extra


def _infer_platform_fit(motives: list[MotiveScore], cfg: dict[str, Any]) -> list[str]:
    fit_cfg = cfg.get("platform_fit") or {}
    scores = {m.key: m.score for m in motives}
    platforms: list[str] = []
    for platform, preferred in fit_cfg.items():
        if any(scores.get(key, 0) >= 6.0 for key in preferred):
            platforms.append(platform)
    return platforms or ["douyin"]


def score_viral_potential(
    *,
    title: str,
    summary: str | None = None,
    content_text: str | None = None,
    prominence_score: float = 0.0,
    story_article_count: int = 1,
    hot_radar_match: Any | None = None,
    config: dict[str, Any] | None = None,
) -> ViralScoreResult:
    root_cfg = config or load_scoring_config()
    viral_cfg = load_viral_scoring_config(root_cfg)
    body = " ".join(filter(None, [title, summary or "", (content_text or "")[:1500]]))

    hook_gate = evaluate_hook_gate(
        title=title,
        summary=summary or "",
        cfg=root_cfg,
        prominence_score=prominence_score,
    )

    raw_motives = {
        "social_currency": _score_social_currency(body, title, viral_cfg),
        "emotional_arousal": _score_motive_from_signals(
            body, "emotional_arousal", viral_cfg, root_cfg=root_cfg
        ),
        "identity": _score_motive_from_signals(body, "identity", viral_cfg, root_cfg=root_cfg),
        "public_issue": _score_motive_from_signals(
            body,
            "public_issue",
            viral_cfg,
            prominence_score=prominence_score,
            root_cfg=root_cfg,
        ),
    }

    motives: list[MotiveScore] = []
    base_total = 0.0
    for key, (score, signals) in raw_motives.items():
        weight = float((viral_cfg.get("motives") or {}).get(key, {}).get("weight", 0.25))
        weighted = score * weight * 10
        base_total += weighted
        motives.append(
            MotiveScore(
                key=key,
                label=MOTIVE_LABELS.get(key, key),
                score=score,
                weight=weight,
                weighted=weighted,
                signals=signals,
            )
        )

    bonuses: list[dict[str, Any]] = []
    bonus_cfg = viral_cfg.get("bonuses") or {}

    social_motive = next((m for m in motives if m.key == "social_currency"), None)
    if social_motive and social_motive.score >= 8.0:
        shock_pts = float(bonus_cfg.get("money_shock", {}).get("points", 20))
        bonuses.append({"reason": "金钱冲击", "points": shock_pts})
        base_total += shock_pts

    emotional_motive = next((m for m in motives if m.key == "emotional_arousal"), None)
    personnel_cfg = bonus_cfg.get("personnel_conflict") or {}
    if emotional_motive and prominence_score >= float(
        personnel_cfg.get("min_prominence_score", 8.0)
    ):
        if emotional_motive.score >= float(personnel_cfg.get("min_emotional_score", 6.0)):
            pts = float(personnel_cfg.get("points", 12))
            bonuses.append({"reason": "人事冲突", "points": pts})
            base_total += pts

    identity_motive = next((m for m in motives if m.key == "identity"), None)
    identity_cfg = bonus_cfg.get("identity_highlight") or {}
    if identity_motive and identity_motive.score >= float(
        identity_cfg.get("min_identity_score", 6.0)
    ):
        pts = float(identity_cfg.get("points", 8))
        bonuses.append({"reason": "人物故事", "points": pts})
        base_total += pts

    base_total += _apply_combo_bonuses(
        body=body,
        motives=motives,
        prominence_score=prominence_score,
        bonuses=bonuses,
        bonus_cfg=bonus_cfg,
    )

    if hot_radar_match is not None:
        rank = int(
            getattr(hot_radar_match, "effective_rank", 0)
            or getattr(hot_radar_match, "rank", 0)
            or 0
        )
        entry_cfg = bonus_cfg.get("hot_radar_entry") or {}
        if rank and rank <= int(entry_cfg.get("max_rank", 20)):
            pts = float(entry_cfg.get("points", 5))
            bonuses.append({"reason": "热榜入场", "points": pts})
            base_total += pts

    multi_cfg = bonus_cfg.get("multi_source") or {}
    if story_article_count >= int(multi_cfg.get("min_articles", 2)):
        pts = float(multi_cfg.get("points", 3))
        bonuses.append({"reason": "多源同题", "points": pts})
        base_total += pts

    all_cfg = bonus_cfg.get("all_motives_present") or {}
    min_score = float(all_cfg.get("min_score", 5.0))
    if all(m.score >= min_score for m in motives):
        pts = float(all_cfg.get("points", 5))
        bonuses.append({"reason": "四维动机齐全", "points": pts})
        base_total += pts

    total = max(0.0, min(100.0, base_total))
    grade = _grade_from_viral_total(total, viral_cfg)

    return ViralScoreResult(
        total=total,
        grade=grade,
        motives=motives,
        hook_gate=hook_gate,
        bonuses=bonuses,
        platform_fit=_infer_platform_fit(motives, viral_cfg),
        recommendation=VIRAL_GRADE_RECOMMENDATIONS.get(grade, "观察"),
    )
