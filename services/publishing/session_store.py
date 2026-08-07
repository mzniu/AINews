"""Encrypted session storage for platform login state."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError as exc:
    raise ImportError(
        "发布中心需要 cryptography 包。请在当前 Python 环境中执行：\n"
        "  python -m pip install \"cryptography>=42.0.0\"\n"
        "或安装全部依赖：\n"
        "  python -m pip install -r requirements.txt"
    ) from exc

from src.utils.config import Config

_KEY_FILE = Config.ROOT_DIR / "data" / "publish" / ".session_key"
_NONCE_SIZE = 12


def _read_key_bytes() -> bytes:
    env_key = os.getenv("PUBLISH_SESSION_KEY", "").strip()
    if env_key:
        try:
            return bytes.fromhex(env_key)
        except ValueError:
            raw = env_key.encode("utf-8")
            if len(raw) < 32:
                raw = raw.ljust(32, b"\0")
            return raw[:32]

    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        data = _KEY_FILE.read_bytes()
        if len(data) >= 32:
            return data[:32]

    key = os.urandom(32)
    _KEY_FILE.write_bytes(key)
    return key


def encrypt_bytes(plaintext: bytes) -> bytes:
    key = _read_key_bytes()
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt_bytes(blob: bytes) -> bytes:
    if len(blob) <= _NONCE_SIZE:
        raise ValueError("invalid encrypted blob")
    key = _read_key_bytes()
    nonce = blob[:_NONCE_SIZE]
    ciphertext = blob[_NONCE_SIZE:]
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def save_encrypted(path: Path, plaintext: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_bytes(plaintext))


def load_encrypted(path: Path) -> bytes:
    return decrypt_bytes(path.read_bytes())
