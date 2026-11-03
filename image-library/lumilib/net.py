"""對外下載（人臉模型、圖像搜尋模型）用的 HTTPS 連線。

打包成 Mac App 後，Python 找不到系統的根憑證，所以 HTTPS 會出現
CERTIFICATE_VERIFY_FAILED。這裡固定使用 certifi 內附的憑證，再加上系統憑證
（公司或防毒軟體自己簽發的憑證通常裝在系統裡）。
"""

from __future__ import annotations

import os
import ssl
import urllib.request

_context: ssl.SSLContext | None = None


def ca_file() -> str | None:
    try:
        import certifi

        path = certifi.where()
        return path if os.path.exists(path) else None
    except Exception:
        return None


def ssl_context() -> ssl.SSLContext:
    global _context
    if _context is None:
        ctx = ssl.create_default_context()  # 系統預設位置（有的話）
        cafile = ca_file()
        if cafile:
            ctx.load_verify_locations(cafile=cafile)
        for extra in ("/etc/ssl/cert.pem", "/opt/homebrew/etc/ca-certificates/cert.pem", "/usr/local/etc/openssl/cert.pem"):
            if os.path.exists(extra):
                try:
                    ctx.load_verify_locations(cafile=extra)
                except (ssl.SSLError, OSError):
                    pass
        _context = ctx
    return _context


def install_default_ca() -> None:
    """讓其他套件（或子程序）也找得到憑證。"""
    cafile = ca_file()
    if cafile and not os.environ.get("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = cafile


def urlopen(url: str | urllib.request.Request, timeout: float = 60):
    req = url if isinstance(url, urllib.request.Request) else urllib.request.Request(
        url, headers={"User-Agent": "LumitakeLibrary"})
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


def describe_error(exc: Exception) -> str:
    text = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in text:
        return ("HTTPS 憑證驗證失敗。如果有使用公司網路、VPN 或防毒軟體的網路防護，請暫時關閉後再試；"
                f"或改用其他網路。（{text}）")
    return text
