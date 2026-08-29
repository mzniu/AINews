"""Shared HTTP helpers for ingestion adapters (retries + timeouts)."""
from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.utils.config import Config

_SESSION: requests.Session | None = None

_RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


def get_ingestion_http_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "HEAD"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _SESSION = session
    return _SESSION


def request_text(
    method: str,
    url: str,
    *,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
    extra_attempts: int = 2,
    **kwargs: Any,
) -> str:
    """Fetch text with urllib3 retries plus manual backoff for connection drops."""
    session = get_ingestion_http_session()
    timeout = timeout if timeout is not None else Config.CRAWLER_TIMEOUT
    last_exc: Exception | None = None
    attempts = max(extra_attempts, 0) + 1
    for attempt in range(attempts):
        try:
            response = session.request(method.upper(), url, timeout=timeout, headers=headers, **kwargs)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(0.8 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def get_text(url: str, **kwargs: Any) -> str:
    return request_text("GET", url, **kwargs)


def post_json(url: str, **kwargs: Any) -> requests.Response:
    session = get_ingestion_http_session()
    timeout = kwargs.pop("timeout", Config.CRAWLER_TIMEOUT)
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = session.post(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt >= 2:
                break
            time.sleep(0.8 * (attempt + 1))
    assert last_exc is not None
    raise last_exc
