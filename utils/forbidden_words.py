"""违禁词配置加载、prompt 渲染与程序扫描。"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "forbidden_words.yaml"
LOCAL_CONFIG_PATH = ROOT_DIR / "config" / "forbidden_words.local.yaml"

CONTENT_FIELD_NAMES = (
    "main_line1",
    "main_line2",
    "sub_title",
    "sub_title2",
    "summary",
    "voiceover_script",
    "tags",
    "highlight_keywords",
    "praise_tags",
    "target_audience",
)

FORBIDDEN_WORDS_HEADER = """【禁限词与合规约束（全局硬性，优先级高于点击率与夸赞效果）】
以下约束适用于全部输出字段：main_line1、main_line2、sub_title、sub_title2、summary、voiceover_script、tags、highlight_keywords、praise_tags、target_audience。任一字段出现下列词汇、同义变体或明显等价表达，均视为严重违规，必须改写后再输出。
"""

CHINESE_ORDINALS = "一二三四五六七八九十"


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    enabled: bool
    severity: str
    match: str
    words: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class Settings:
    hot_reload: bool = True
    default_severity: str = "error"
    on_violation: str = "retry_once"
    max_retry: int = 1
    inject_to_prompt: bool = True
    post_check: bool = True


@dataclass(frozen=True)
class Violation:
    field: str
    category_id: str
    category_name: str
    matched: str
    severity: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "field": self.field,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "matched": self.matched,
            "severity": self.severity,
        }


@dataclass
class ForbiddenWordsRegistry:
    settings: Settings
    policy: List[str]
    categories: List[Category]
    _source_mtimes: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, *, force: bool = False) -> "ForbiddenWordsRegistry":
        del force
        base_data = _load_yaml_file(DEFAULT_CONFIG_PATH)
        local_data = _load_yaml_file(LOCAL_CONFIG_PATH) if LOCAL_CONFIG_PATH.exists() else {}
        merged = _merge_config(base_data, local_data)
        settings = _parse_settings(merged.get("settings") or {})
        policy = [str(item).strip() for item in (merged.get("policy") or []) if str(item).strip()]
        categories = _parse_categories(merged.get("categories") or [], settings.default_severity)
        mtimes = {
            str(DEFAULT_CONFIG_PATH): _safe_mtime(DEFAULT_CONFIG_PATH),
        }
        if LOCAL_CONFIG_PATH.exists():
            mtimes[str(LOCAL_CONFIG_PATH)] = _safe_mtime(LOCAL_CONFIG_PATH)
        return cls(settings=settings, policy=policy, categories=categories, _source_mtimes=mtimes)

    def maybe_reload(self) -> bool:
        if not self.settings.hot_reload:
            return False
        current = {
            str(DEFAULT_CONFIG_PATH): _safe_mtime(DEFAULT_CONFIG_PATH),
        }
        if LOCAL_CONFIG_PATH.exists():
            current[str(LOCAL_CONFIG_PATH)] = _safe_mtime(LOCAL_CONFIG_PATH)
        if current == self._source_mtimes:
            return False
        refreshed = ForbiddenWordsRegistry.load()
        self.settings = refreshed.settings
        self.policy = refreshed.policy
        self.categories = refreshed.categories
        self._source_mtimes = refreshed._source_mtimes
        return True

    def enabled_categories(self) -> List[Category]:
        return [category for category in self.categories if category.enabled]

    def build_prompt_section(self) -> str:
        lines = [FORBIDDEN_WORDS_HEADER.rstrip()]
        for index, category in enumerate(self.enabled_categories(), start=1):
            lines.append(f"{_to_chinese_ordinal(index)}、{category.name}")
            if category.words:
                lines.append(f"- {'、'.join(category.words)}")
            if category.patterns:
                lines.append("- 正则模式：" + "、".join(pattern.pattern for pattern in category.patterns))
            if category.notes:
                lines.append(f"- 说明：{category.notes}")
        if self.policy:
            lines.append(f"{_to_chinese_ordinal(len(self.enabled_categories()) + 1)}、改写原则")
            for item in self.policy:
                lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    def scan_text(self, text: str, *, field: str) -> List[Violation]:
        if not text or not self.settings.post_check:
            return []
        normalized = _normalize_field_text(text, field=field)
        if not normalized:
            return []
        violations: List[Violation] = []
        for category in self.enabled_categories():
            for word in category.words:
                if word and word in normalized:
                    violations.append(
                        Violation(
                            field=field,
                            category_id=category.id,
                            category_name=category.name,
                            matched=word,
                            severity=category.severity,
                        )
                    )
            for pattern in category.patterns:
                match = pattern.search(normalized)
                if match:
                    violations.append(
                        Violation(
                            field=field,
                            category_id=category.id,
                            category_name=category.name,
                            matched=match.group(0),
                            severity=category.severity,
                        )
                    )
        return violations

    def scan_fields(self, fields: Dict[str, Any]) -> List[Violation]:
        violations: List[Violation] = []
        for field_name in CONTENT_FIELD_NAMES:
            value = fields.get(field_name)
            if value is None:
                continue
            if isinstance(value, list):
                for item in value:
                    text = str(item or "").strip()
                    if text:
                        violations.extend(self.scan_text(text, field=field_name))
            else:
                text = str(value or "").strip()
                if text:
                    violations.extend(self.scan_text(text, field=field_name))
        return violations

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "settings": {
                "hot_reload": self.settings.hot_reload,
                "default_severity": self.settings.default_severity,
                "on_violation": self.settings.on_violation,
                "max_retry": self.settings.max_retry,
                "inject_to_prompt": self.settings.inject_to_prompt,
                "post_check": self.settings.post_check,
            },
            "policy": list(self.policy),
            "categories": [
                {
                    "id": category.id,
                    "name": category.name,
                    "enabled": category.enabled,
                    "severity": category.severity,
                    "match": category.match,
                    "words": list(category.words),
                    "pattern_count": len(category.patterns),
                    "notes": category.notes,
                }
                for category in self.categories
            ],
        }


_registry: Optional[ForbiddenWordsRegistry] = None
_registry_lock = threading.Lock()


def get_registry(*, force_reload: bool = False) -> ForbiddenWordsRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ForbiddenWordsRegistry.load()
        elif force_reload:
            _registry = ForbiddenWordsRegistry.load()
        else:
            _registry.maybe_reload()
        return _registry


def reload_registry() -> ForbiddenWordsRegistry:
    return get_registry(force_reload=True)


def scan_content_fields(
    fields: Dict[str, Any],
    *,
    registry: Optional[ForbiddenWordsRegistry] = None,
) -> List[Violation]:
    active = registry or get_registry()
    return active.scan_fields(fields)


def partition_violations(violations: Sequence[Violation]) -> tuple[List[Violation], List[Violation]]:
    errors = [item for item in violations if item.severity == "error"]
    warnings = [item for item in violations if item.severity != "error"]
    return errors, warnings


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _parse_settings(raw: Dict[str, Any]) -> Settings:
    return Settings(
        hot_reload=bool(raw.get("hot_reload", True)),
        default_severity=str(raw.get("default_severity", "error")),
        on_violation=str(raw.get("on_violation", "retry_once")),
        max_retry=max(0, int(raw.get("max_retry", 1))),
        inject_to_prompt=bool(raw.get("inject_to_prompt", True)),
        post_check=bool(raw.get("post_check", True)),
    )


def _parse_categories(raw_categories: Iterable[Any], default_severity: str) -> List[Category]:
    by_id: Dict[str, Category] = {}
    for raw in raw_categories:
        if not isinstance(raw, dict):
            continue
        category_id = str(raw.get("id") or "").strip()
        if not category_id:
            continue
        words = tuple(
            str(word).strip()
            for word in (raw.get("words") or [])
            if str(word).strip()
        )
        patterns: List[re.Pattern[str]] = []
        match_mode = str(raw.get("match") or "substring").strip().lower()
        for pattern in raw.get("patterns") or []:
            pattern_text = str(pattern).strip()
            if pattern_text:
                patterns.append(re.compile(pattern_text))
        category = Category(
            id=category_id,
            name=str(raw.get("name") or category_id).strip(),
            enabled=bool(raw.get("enabled", True)),
            severity=str(raw.get("severity") or default_severity).strip() or default_severity,
            match=match_mode,
            words=words,
            patterns=tuple(patterns),
            notes=str(raw.get("notes") or "").strip(),
        )
        if category_id in by_id:
            existing = by_id[category_id]
            merged_words = tuple(dict.fromkeys(existing.words + category.words))
            merged_patterns = existing.patterns + category.patterns
            by_id[category_id] = Category(
                id=category_id,
                name=category.name or existing.name,
                enabled=category.enabled if "enabled" in raw else existing.enabled,
                severity=category.severity or existing.severity,
                match=category.match or existing.match,
                words=merged_words,
                patterns=merged_patterns,
                notes=category.notes or existing.notes,
            )
        else:
            by_id[category_id] = category
    return list(by_id.values())


def _merge_config(base: Dict[str, Any], local: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    local_settings = local.get("settings")
    if isinstance(local_settings, dict):
        merged_settings = dict(merged.get("settings") or {})
        merged_settings.update(local_settings)
        merged["settings"] = merged_settings
    local_policy = local.get("policy")
    if isinstance(local_policy, list) and local_policy:
        merged_policy = list(merged.get("policy") or [])
        merged_policy.extend(str(item).strip() for item in local_policy if str(item).strip())
        merged["policy"] = merged_policy
    merged_categories = list(merged.get("categories") or [])
    local_categories = local.get("categories")
    if isinstance(local_categories, list):
        merged_categories.extend(local_categories)
    merged["categories"] = merged_categories
    return merged


def _normalize_field_text(text: str, *, field: str) -> str:
    normalized = str(text or "").strip()
    if field == "tags":
        normalized = normalized.replace("#", "")
    return normalized


def _to_chinese_ordinal(number: int) -> str:
    if number <= 0:
        return str(number)
    if number <= 10:
        return CHINESE_ORDINALS[number - 1]
    if number < 20:
        return "十" + CHINESE_ORDINALS[number - 11]
    tens, ones = divmod(number, 10)
    prefix = CHINESE_ORDINALS[tens - 1] + "十"
    return prefix if ones == 0 else prefix + CHINESE_ORDINALS[ones - 1]
