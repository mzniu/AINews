"""Xiaohongshu note metrics parsing and fetch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from services.publishing.metrics.adapters.base import MetricsAdapter, PostMetricsItem
from services.publishing.metrics.adapters.common import (
    build_post_metrics_items_from_rows,
    fetch_metrics_rows_with_session,
)
from services.publishing.metrics.post_id import build_xiaohongshu_post_url

NOTE_MANAGER_URL = "https://creator.xiaohongshu.com/new/note-manager"

_EXTRACT_ROWS_JS = """
() => {
  const rows = [];
  const seen = new Set();
  const pushRow = (row) => {
    const id = String(row.note_id || row.platform_post_id || '').trim();
    if (!id || seen.has(id)) return;
    seen.add(id);
    rows.push(row);
  };

  const parseCard = (el) => {
    const noteId = el.getAttribute('data-note-id')
      || el.getAttribute('data-id')
      || el.dataset?.noteId
      || el.dataset?.id;
    if (!noteId) return;
    const titleEl = el.querySelector('[class*="title"], .title, h3, h4');
    const title = titleEl ? titleEl.textContent.trim() : '';
    const text = el.innerText || '';
    const readMatch = text.match(/阅读\\s*([\\d.,]+万?)/);
    const likeMatch = text.match(/点赞\\s*([\\d.,]+万?)/);
    const commentMatch = text.match(/评论\\s*([\\d.,]+万?)/);
    const favMatch = text.match(/收藏\\s*([\\d.,]+万?)/);
    pushRow({
      note_id: noteId,
      title,
      read_count: readMatch ? readMatch[1] : null,
      like_count: likeMatch ? likeMatch[1] : null,
      comment_count: commentMatch ? commentMatch[1] : null,
      favorite_count: favMatch ? favMatch[1] : null,
    });
  };

  document.querySelectorAll('[data-note-id], [data-id]').forEach(parseCard);
  document.querySelectorAll('tr').forEach((tr) => {
    const link = tr.querySelector('a[href*="note"], a[href*="explore"]');
    if (!link) return;
    const href = link.getAttribute('href') || '';
    const m = href.match(/(?:noteId=|explore\\/)([A-Za-z0-9]+)/);
    if (!m) return;
    const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim());
    pushRow({
      note_id: m[1],
      title: cells[0] || link.textContent.trim(),
      read_count: cells.find(t => /\\d/.test(t)) || null,
      like_count: cells[1] || null,
      comment_count: cells[2] || null,
      favorite_count: cells[3] || null,
    });
  });

  if (rows.length === 0 && window.__INITIAL_STATE__) {
    try {
      const state = window.__INITIAL_STATE__;
      const list = state?.note?.noteList
        || state?.noteList
        || state?.data?.notes
        || [];
      for (const note of list) {
        pushRow({
          note_id: note.id || note.noteId,
          title: note.title || note.displayTitle || '',
          published_at: note.time || note.publishTime || note.createTime || null,
          read_count: note.readCount ?? note.viewCount ?? note.reads,
          like_count: note.likeCount ?? note.likes,
          comment_count: note.commentCount ?? note.comments,
          favorite_count: note.collectCount ?? note.favCount,
        });
      }
    } catch (e) {}
  }
  return rows;
}
"""


def build_xiaohongshu_metrics_items_from_rows(rows: list[dict[str, Any]]) -> list[PostMetricsItem]:
    return build_post_metrics_items_from_rows(
        rows,
        id_keys=("note_id", "platform_post_id"),
        post_url_builder=build_xiaohongshu_post_url,
    )


class XiaohongshuMetricsAdapter(MetricsAdapter):
    platform_id = "xiaohongshu"

    def fetch_recent_post_metrics(
        self,
        session_path: Path,
        *,
        since_days: int = 90,
        limit: int = 100,
        needed_post_ids: set[str] | None = None,
    ) -> list[PostMetricsItem]:
        del since_days
        rows = fetch_metrics_rows_with_session(
            session_path,
            list_url=NOTE_MANAGER_URL,
            extract_js=_EXTRACT_ROWS_JS,
            platform_label="Xiaohongshu",
            limit=limit,
            paginate=True,
            needed_ids=needed_post_ids,
        )
        items = build_xiaohongshu_metrics_items_from_rows(rows)
        logger.info("Xiaohongshu metrics parsed {} item(s)", len(items))
        return items
