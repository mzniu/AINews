from pathlib import Path

from services.publishing.session_store import decrypt_bytes, encrypt_bytes, load_encrypted, save_encrypted


def test_roundtrip(tmp_path, monkeypatch):
    key_file = tmp_path / "data" / "publish" / ".session_key"
    key_file.parent.mkdir(parents=True)
    key_file.write_bytes(b"a" * 32)
    monkeypatch.setenv("PUBLISH_SESSION_KEY", "")
    monkeypatch.setattr("services.publishing.session_store._KEY_FILE", key_file)

    plain = b'{"cookies":[]}'
    blob = encrypt_bytes(plain)
    assert decrypt_bytes(blob) == plain
    out = tmp_path / "sess.enc"
    save_encrypted(out, plain)
    assert load_encrypted(out) == plain
