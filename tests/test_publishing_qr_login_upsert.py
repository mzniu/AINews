from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.publishing.adapters.base import AccountInfo
from services.publishing.qr_login import _upsert_account
from src.db.models.publishing import PublisherAccount


def test_upsert_account_calls_adapter_persist(monkeypatch, tmp_path):
    from src.utils.config import Config

    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    (tmp_path / "data" / "publish" / "sessions").mkdir(parents=True)

    mock_adapter = MagicMock()
    monkeypatch.setattr(
        "services.publishing.qr_login.get_adapter",
        lambda platform: mock_adapter,
    )

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None

    account_info = AccountInfo(nickname="测试", platform_uid="dy_test_1", avatar_url=None)

    account = _upsert_account(
        session,
        platform="douyin",
        purpose="create",
        existing_account_id=None,
        account_info=account_info,
        storage_state_json=b'{"cookies":[]}',
    )

    assert isinstance(account, PublisherAccount)
    mock_adapter.persist_storage_state.assert_called_once()
    dest_path, payload = mock_adapter.persist_storage_state.call_args[0]
    assert dest_path.name.endswith(".enc")
    assert payload == b'{"cookies":[]}'
