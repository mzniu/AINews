from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.publishing.adapters.base import AccountInfo
from services.publishing.qr_login import _upsert_account
from src.db.models.publishing import PublisherAccount


def test_upsert_account_calls_adapter_persist(monkeypatch, tmp_path):
    from src.utils import paths
    from src.utils.config import Config

    data_dir = tmp_path / "data"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    paths.get_data_dir.cache_clear()
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    (data_dir / "publish" / "sessions").mkdir(parents=True)

    mock_adapter = MagicMock()
    monkeypatch.setattr(
        "services.publishing.qr_login.get_adapter",
        lambda platform: mock_adapter,
    )

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None

    def _assign_id_on_flush():
        for call in session.add.call_args_list:
            obj = call[0][0]
            if getattr(obj, "id", None) in (None, ""):
                obj.id = "acc1"

    session.flush.side_effect = lambda: _assign_id_on_flush()

    account_info = AccountInfo(nickname="测试", platform_uid="dy_test_1", avatar_url=None)

    account = _upsert_account(
        session,
        platform="douyin",
        purpose="create",
        existing_account_id=None,
        account_info=account_info,
        storage_state_json=b'{"cookies":[]}',
        qr_session_id="qr1",
    )

    assert isinstance(account, PublisherAccount)
    assert account.browser_profile_path == "data/publish/profiles/acc1"
    mock_adapter.persist_storage_state.assert_called_once()
    dest_path, payload = mock_adapter.persist_storage_state.call_args[0]
    assert dest_path.name.endswith(".enc")
    assert payload == b'{"cookies":[]}'
