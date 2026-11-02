"""手機／平板連線用的登入：密碼以 scrypt 雜湊保存，登入後發簽章 cookie。

在這台 Mac 本機開啟（127.0.0.1）不需要登入；從區網其他裝置連線時一律需要密碼。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

COOKIE = "lumilib_session"
SESSION_DAYS = 30


class Auth:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if "secret" not in data:
            data["secret"] = secrets.token_hex(32)
            self._save(data)
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    @property
    def has_password(self) -> bool:
        return bool(self.data.get("password"))

    @staticmethod
    def _hash(password: str, salt: bytes) -> str:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()

    def set_password(self, password: str) -> None:
        if len(password) < 6:
            raise ValueError("密碼至少 6 個字元")
        salt = secrets.token_bytes(16)
        self.data["password"] = {"salt": salt.hex(), "hash": self._hash(password, salt)}
        # 換密碼後舊的登入全部失效
        self.data["secret"] = secrets.token_hex(32)
        self._save(self.data)

    def check_password(self, password: str) -> bool:
        stored = self.data.get("password")
        if not stored:
            return False
        return hmac.compare_digest(stored["hash"], self._hash(password, bytes.fromhex(stored["salt"])))

    def issue(self) -> str:
        expires = int(time.time()) + SESSION_DAYS * 86400
        payload = f"{expires}.{secrets.token_hex(8)}"
        sig = hmac.new(self.data["secret"].encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def verify(self, token: str | None) -> bool:
        if not token or token.count(".") != 2:
            return False
        expires, nonce, sig = token.split(".")
        payload = f"{expires}.{nonce}"
        expected = hmac.new(self.data["secret"].encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return expires.isdigit() and int(expires) > time.time()
