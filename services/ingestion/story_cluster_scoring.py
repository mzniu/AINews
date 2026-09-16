"""Enhanced pair scoring: rules + embedding + optional LLM gray-zone."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.ingestion.story_cluster_embedding import embedding_similarity
from services.ingestion.story_cluster_llm import adjudicate_same_story
from services.ingestion.story_cluster_config import load_story_cluster_config
from src.db.models.ingestion import IngestedArticle


@dataclass
class PairMatchResult:
    should_match: bool
    final_score: float
    rule_score: float
    embedding_score: float
    blended_score: float
    cluster_method: str
    llm: dict[str, Any] | None = None


def score_pair_rule(article: IngestedArticle, other: IngestedArticle) -> float:
    from services.ingestion.story_cluster import score_pair

    return score_pair(article, other)


def evaluate_pair_match(
    article: IngestedArticle,
    other: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
) -> PairMatchResult:
    cfg = config or load_story_cluster_config()
    threshold = float(cfg.get("title_threshold", 0.72))
    gray_low = float(cfg.get("gray_low", 0.55))

    rule_score = score_pair_rule(article, other)
    embed_score = embedding_similarity(article, other, config=cfg)

    embed_cfg = cfg.get("embedding") or {}
    if embed_cfg.get("enabled", True):
        rule_weight = float(embed_cfg.get("rule_weight", 0.55))
        embed_weight = float(embed_cfg.get("embedding_weight", 0.45))
        blended = rule_score * rule_weight + embed_score * embed_weight
        cluster_method = "rule+embedding"
    else:
        blended = rule_score
        cluster_method = "rule"

    if blended >= threshold:
        return PairMatchResult(
            should_match=True,
            final_score=blended,
            rule_score=rule_score,
            embedding_score=embed_score,
            blended_score=blended,
            cluster_method=cluster_method,
        )

    if blended < gray_low:
        return PairMatchResult(
            should_match=False,
            final_score=blended,
            rule_score=rule_score,
            embedding_score=embed_score,
            blended_score=blended,
            cluster_method=cluster_method,
        )

    llm_cfg = cfg.get("llm") or {}
    if not llm_cfg.get("enabled", True):
        return PairMatchResult(
            should_match=False,
            final_score=blended,
            rule_score=rule_score,
            embedding_score=embed_score,
            blended_score=blended,
            cluster_method=cluster_method,
        )

    llm_result = adjudicate_same_story(
        article,
        other,
        rule_score=rule_score,
        blended_score=blended,
    )
    if llm_result is None:
        return PairMatchResult(
            should_match=False,
            final_score=blended,
            rule_score=rule_score,
            embedding_score=embed_score,
            blended_score=blended,
            cluster_method=cluster_method,
        )

    min_conf = float(llm_cfg.get("min_confidence", 0.7))
    same_story = bool(llm_result.get("same_story"))
    confidence = float(llm_result.get("confidence") or 0)
    if confidence >= min_conf:
        return PairMatchResult(
            should_match=same_story,
            final_score=blended,
            rule_score=rule_score,
            embedding_score=embed_score,
            blended_score=blended,
            cluster_method="rule+embedding+llm",
            llm=llm_result,
        )

    return PairMatchResult(
        should_match=False,
        final_score=blended,
        rule_score=rule_score,
        embedding_score=embed_score,
        blended_score=blended,
        cluster_method=cluster_method,
        llm=llm_result,
    )
