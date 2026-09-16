"""Regenerate reply_text for all pending_approval comment inbox rows."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator
from src.db.engine import get_session_factory


def main() -> None:
    result = CommentReplyOrchestrator(get_session_factory()).regenerate_pending_replies()
    print(result)


if __name__ == "__main__":
    main()
