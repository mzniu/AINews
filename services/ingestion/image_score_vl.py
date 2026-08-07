"""Vision-model batch scoring for article images."""
from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from services.ingestion.image_scorer import load_image_scoring_config
from services.model_config.registry import get_vision_client

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    match = _JSON_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _fix_trailing_commas(text: str) -> str:
    previous = None
    current = text
    while previous != current:
        previous = current
        current = _TRAILING_COMMA_RE.sub(r"\1", current)
    return current


def _load_json_payload(text: str) -> dict[str, Any] | None:
    cleaned = _strip_code_fence(text)
    if not cleaned:
        return None

    candidates = [cleaned]
    match = _JSON_BLOCK_RE.search(cleaned)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        variants = [candidate, _fix_trailing_commas(candidate)]
        for variant in variants:
            try:
                data = json.loads(variant)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    return None


def _resolve_max_tokens(
    profile: dict[str, Any],
    *,
    image_count: int,
    vl_cfg: dict[str, Any],
) -> int:
    per_image = int(vl_cfg.get("max_tokens_per_image", 700))
    floor = int(vl_cfg.get("min_max_tokens", 2048))
    ceiling = int(vl_cfg.get("max_max_tokens", 8192))
    profile_default = int(profile.get("max_tokens") or floor)
    needed = per_image * max(1, image_count) + 256
    return min(ceiling, max(floor, profile_default, needed))


def _build_prompt(
    *,
    article_title: str,
    article_summary: str | None,
    keywords: list[str],
    content_excerpt: str | None,
    image_ids: list[str],
) -> str:
    kw = "、".join(keywords[:8]) if keywords else "无"
    ids = ", ".join(image_ids)
    return f"""你是 AI 快讯短视频的配图编辑。目标成片为 **8–12 秒**，通常只选 **3–4 张主画面**（每张约 2–3 秒），**不要**章节标题图、小节过渡图、纯装饰分隔图。

请评估以下图片在「当前文章」语境下，是否适合作为短视频主画面。

【文章】
标题：{article_title}
摘要：{article_summary or "无"}
关键词：{kw}
正文节选：{content_excerpt or "无"}

【待评图片 ID】
{ids}

请对每张图输出 7 个维度（0-10 整数）：
- topic_relevance：与文章主题相关度（核心事实/产品/事件）
- info_value：信息价值（产品截图、数据图表、现场图 > 纯装饰）
- visual_quality：画质可用性
- flash_fit：**短视频主画面适配**（主体突出、信息密度适中、适合 2–3 秒一镜、非标题卡/过渡图）
- cover_fit：是否适合作为封面缩略图（权重较低，仅作参考）
- figure_prominence：重要人物/争议人物是否清晰出镜（无人物则低分）
- compliance：合规（水印/广告/logo）

**强烈不推荐**（可在 penalties 中标注）：
- 章节标题、小节标题、目录、过渡装饰、纯文字大图 → reason: chapter_title 或 transition_decor
- 与正文无关的插图、分隔线、页眉页脚装饰

横图更适合视频画幅；若画面本身为 GIF/动图或强动态内容，在 flash_fit 与 verdict 中体现优势。
可附加 penalties 数组（reason + points）。reject=true 表示强烈不建议使用。

**输出要求（必须遵守）**：
- 仅输出一个 JSON 对象，不要 Markdown、不要解释文字
- 键名与字符串一律使用双引号，禁止尾随逗号
- caption / verdict 中如有引号请转义

只输出 JSON，格式：
{{
  "images": [
    {{
      "source_id": "图片ID",
      "dimensions": {{
        "topic_relevance": {{"score": 8, "signals": ["信号"]}},
        "info_value": {{"score": 7, "signals": []}},
        "visual_quality": {{"score": 9, "signals": []}},
        "flash_fit": {{"score": 9, "signals": ["适合2-3秒主画面"]}},
        "cover_fit": {{"score": 7, "signals": []}},
        "figure_prominence": {{"score": 7, "signals": ["人物出镜"]}},
        "compliance": {{"score": 9, "signals": []}}
      }},
      "penalties": [],
      "caption": "一句话描述图片内容",
      "verdict": "一句话配图建议（是否适合进 3–4 张主画面）",
      "reject": false
    }}
  ]
}}"""


def _encode_image_data_url(path: Path, *, max_edge_px: int = 1280) -> str:
    from PIL import Image

    with Image.open(path) as img:
        img = img.convert("RGB")
        w, h = img.size
        longest = max(w, h)
        if longest > max_edge_px:
            scale = max_edge_px / longest
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _parse_vl_response(raw: str, *, expected_ids: list[str]) -> list[dict[str, Any]]:
    data = _load_json_payload(raw or "")
    if data is None:
        logger.warning(f"VL JSON parse failed: {(raw or '')[:200]}")
        return []

    images = data.get("images")
    if not isinstance(images, list):
        return []

    by_id: dict[str, dict[str, Any]] = {}
    for item in images:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("source_id") or "").strip()
        if sid:
            by_id[sid] = item

    out: list[dict[str, Any]] = []
    for sid in expected_ids:
        if sid in by_id:
            out.append(by_id[sid])
    return out


def _call_vl_batch(
    *,
    client: Any,
    profile: dict[str, Any],
    prompt: str,
    images: list[tuple[str, Path]],
    max_edge_px: int,
    timeout_sec: int,
    max_tokens: int,
    use_json_mode: bool = True,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for source_id, path in images:
        content.append({"type": "text", "text": f"图片 ID: {source_id}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _encode_image_data_url(path, max_edge_px=max_edge_px)},
            }
        )

    request_kwargs: dict[str, Any] = {
        "model": profile["model"],
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": float(profile.get("temperature") if profile.get("temperature") is not None else 0.3),
        "timeout": timeout_sec,
    }
    if use_json_mode and profile.get("json_mode", True):
        request_kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**request_kwargs)
    except Exception as exc:
        if "response_format" in request_kwargs:
            logger.debug(f"VL json_mode unsupported, retrying without it: {exc}")
            request_kwargs.pop("response_format", None)
            response = client.chat.completions.create(**request_kwargs)
        else:
            raise

    raw = response.choices[0].message.content or ""
    expected_ids = [sid for sid, _ in images]
    parsed = _parse_vl_response(raw, expected_ids=expected_ids)
    if not parsed and raw.strip():
        logger.warning(
            f"VL response parsed empty for {len(images)} image(s); preview: {raw[:240]}"
        )
    return parsed


def _score_single_images(
    *,
    client: Any,
    profile: dict[str, Any],
    article_title: str,
    article_summary: str | None,
    keywords: list[str],
    content_excerpt: str | None,
    images: list[tuple[str, Path]],
    max_edge_px: int,
    timeout_sec: int,
    max_tokens: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for source_id, path in images:
        prompt = _build_prompt(
            article_title=article_title,
            article_summary=article_summary,
            keywords=keywords,
            content_excerpt=content_excerpt,
            image_ids=[source_id],
        )
        try:
            batch = _call_vl_batch(
                client=client,
                profile=profile,
                prompt=prompt,
                images=[(source_id, path)],
                max_edge_px=max_edge_px,
                timeout_sec=timeout_sec,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning(f"VL single call failed for {source_id}: {exc}")
            continue
        if batch:
            results.extend(batch)
    return results


def _resolve_vl_timeouts(vl_cfg: dict[str, Any], *, image_count: int) -> tuple[int, int]:
    """Return (batch_timeout_sec, single_timeout_sec)."""
    legacy = int(vl_cfg.get("request_timeout_sec", 60))
    single_timeout = int(vl_cfg.get("single_timeout_sec") or legacy)
    batch_timeout = int(vl_cfg.get("batch_timeout_sec") or max(legacy, single_timeout * 2))
    if image_count <= 1:
        return single_timeout, single_timeout
    return batch_timeout, single_timeout


def score_images_batch(
    *,
    article_title: str,
    article_summary: str | None,
    keywords: list[str],
    content_excerpt: str | None,
    images: list[tuple[str, Path]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Score a batch of images. Each item in images is (source_id, local_path)."""
    if not images:
        return []

    client, profile = get_vision_client()
    if client is None or profile is None:
        raise RuntimeError("未配置可用的视觉模型（请填写 API Key 并启用）")

    cfg = config or load_image_scoring_config()
    vl_cfg = cfg.get("vl") or {}
    max_edge_px = int(vl_cfg.get("max_edge_px", 960))
    batch_timeout_sec, single_timeout_sec = _resolve_vl_timeouts(vl_cfg, image_count=len(images))
    max_tokens = _resolve_max_tokens(profile, image_count=len(images), vl_cfg=vl_cfg)
    max_retries = max(0, int(vl_cfg.get("max_retries", 1)))
    fallback_to_single = bool(vl_cfg.get("fallback_to_single", True))

    prompt = _build_prompt(
        article_title=article_title,
        article_summary=article_summary,
        keywords=keywords,
        content_excerpt=content_excerpt,
        image_ids=[sid for sid, _ in images],
    )

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            parsed = _call_vl_batch(
                client=client,
                profile=profile,
                prompt=prompt,
                images=images,
                max_edge_px=max_edge_px,
                timeout_sec=batch_timeout_sec,
                max_tokens=max_tokens,
            )
            if parsed:
                return parsed
            last_exc = RuntimeError("VL batch returned empty or unparseable JSON")
        except Exception as exc:
            last_exc = exc
            logger.warning(
                f"VL batch call failed (attempt {attempt + 1}/{max_retries + 1}, "
                f"{len(images)} images, timeout={batch_timeout_sec}s, max_tokens={max_tokens}): {exc}"
            )

    if len(images) <= 1 or not fallback_to_single:
        if last_exc is not None:
            logger.warning(f"VL scoring gave up after batch attempts: {last_exc}")
        return []

    logger.info(
        f"VL batch failed, falling back to single-image calls "
        f"({len(images)} images, timeout={single_timeout_sec}s each)"
    )
    return _score_single_images(
        client=client,
        profile=profile,
        article_title=article_title,
        article_summary=article_summary,
        keywords=keywords,
        content_excerpt=content_excerpt,
        images=images,
        max_edge_px=max_edge_px,
        timeout_sec=single_timeout_sec,
        max_tokens=max_tokens,
    )
