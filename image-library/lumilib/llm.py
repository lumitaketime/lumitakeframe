"""助理用的語言模型：這台電腦的 Ollama（預設，離線），或使用者自己選的服務。

服務：
- ollama：這台電腦上的 Ollama，資料不離開這台電腦。
- claude：Anthropic 的 Claude，用官方的 Python 套件（原生的 Messages API）。
- gemini：Google 的 Gemini，經由 Google 官方提供的 OpenAI 相容入口。
- openai：OpenAI。
- custom：其他 OpenAI 相容的服務（本機的 LM Studio、llama.cpp server，或其他雲端服務），網址自己填。

雲端服務會收到問題、檔名，以及（使用者允許時）文件片段；切換前介面一定先請本人確認（核心原則二）。
API 金鑰只存在這台電腦的設定檔（只有自己能讀），介面拿不到原本的金鑰。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .analyzer import OllamaUnavailable, parse_model_json

# 服務的固定資料：網址、要不要金鑰、Claude 的模型清單
PROVIDERS = {
    "ollama": {"local": True},
    "claude": {"url": "https://api.anthropic.com", "key": True},
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai", "key": True},
    "openai": {"url": "https://api.openai.com/v1", "key": True},
    "custom": {"key": False},
}
CLOUD = ("claude", "gemini", "openai")

# Claude 的模型（由聰明到便宜）；價格是每一百萬 token 的美元（輸入／輸出），只用來在介面上提示
CLAUDE_MODELS = [
    {"id": "claude-opus-5-5", "name": "Claude Opus 5.5", "price": [4, 20], "note": "best"},
    {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "price": [2, 10], "note": "balanced"},
    {"id": "claude-haiku-5-5", "name": "Claude Haiku 5.5", "price": [0.1, 0.5], "note": "cheap"},
]
CLAUDE_DEFAULT = "claude-opus-5-5"
# 這兩個模型可以請 Anthropic 在拒絕回答時自動改用其他模型重試（伺服器端的備援）
CLAUDE_FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")
CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"

KEY_SETTINGS = {"claude": "assistant_claude_key", "gemini": "assistant_gemini_key", "openai": "assistant_openai_key",
                "custom": "assistant_api_key"}
MODEL_SETTINGS = {"claude": "assistant_claude_model", "gemini": "assistant_gemini_model", "openai": "assistant_openai_model",
                  "custom": "assistant_api_model"}


def is_local_url(url: str) -> bool:
    """網址是不是這台電腦（資料不會離開）。"""
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1") or host.endswith(".local")


def provider_of(cfg) -> str:
    """現在用哪個服務。舊版只有「openai」一種（其實是任何 OpenAI 相容的網址），沒有存 OpenAI 金鑰的話當成「其他相容服務」。"""
    p = getattr(cfg, "assistant_provider", "") or "ollama"
    if p == "openai" and not getattr(cfg, "assistant_openai_key", "") and getattr(cfg, "assistant_api_url", ""):
        return "custom"
    return p if p in PROVIDERS else "ollama"


def api_settings(cfg, provider: str) -> dict:
    """某個服務的網址、模型、金鑰。"""
    if provider == "custom":
        url = cfg.assistant_api_url
    else:
        url = PROVIDERS.get(provider, {}).get("url", "")
    model = (getattr(cfg, MODEL_SETTINGS[provider], "") or "") if provider in MODEL_SETTINGS else ""
    if provider == "claude" and not model:
        model = CLAUDE_DEFAULT
    key = (getattr(cfg, KEY_SETTINGS[provider], "") or "") if provider in KEY_SETTINGS else ""
    return {"url": url, "model": model, "key": key}


def is_remote(cfg) -> bool:
    p = provider_of(cfg)
    if p == "ollama":
        return False
    if p == "custom":
        return bool(cfg.assistant_api_url) and not is_local_url(cfg.assistant_api_url)
    return True


# ---- 這台電腦的 Ollama ----

class OllamaLLM:
    def __init__(self, client, base_url: str, model: str):
        self.client, self.base_url, self.model = client, base_url, model
        self.remote = False

    def plan_json(self, prompt: str, schema: dict) -> dict:
        return self.client.chat_json(self.model, prompt, schema, timeout=180, num_predict=500)

    def stream(self, messages: list[dict]):
        payload = {"model": self.model, "messages": messages, "stream": True, "keep_alive": "15m", "think": False,
                   "options": {"temperature": 0.3, "num_ctx": 8192, "num_predict": 1200}}
        for event in _post_ollama(self.base_url, payload):
            if event.get("error"):
                raise RuntimeError(str(event["error"]))
            text = (event.get("message") or {}).get("content") or ""
            if text:
                yield text

    def complete(self, prompt: str, max_tokens: int = 50) -> str:
        return "".join(self.stream([{"role": "user", "content": prompt}]))[:500]


def _post_ollama(base_url: str, payload: dict, timeout: int = 300):
    req = urllib.request.Request(base_url.rstrip("/") + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        if exc.code == 404:
            raise OllamaUnavailable(f"模型「{payload.get('model')}」還沒下載。") from exc
        raise RuntimeError(f"Ollama 回應 {exc.code}：{body[:200]}") from exc
    except (urllib.error.URLError, ConnectionError) as exc:
        raise OllamaUnavailable("沒有連到 Ollama。請打開 Ollama 後再試一次。") from exc
    with resp:
        for line in resp:
            if line.strip():
                yield json.loads(line.decode("utf-8"))


# ---- OpenAI 相容的服務（Gemini、OpenAI、LM Studio、其他） ----

class OpenAILLM:
    def __init__(self, base_url: str, model: str, key: str = "", name: str = ""):
        self.base_url, self.model, self.key = base_url.rstrip("/"), model, key
        self.name = name or (urlparse(base_url).hostname or base_url)
        self.remote = not is_local_url(base_url)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def _request(self, payload: dict, timeout: int = 120):
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
                                     headers=self._headers(), method="POST")
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc, self.model) from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise OllamaUnavailable(f"連不到 {self.name}。請確認網路或服務有開啟、網址正確。") from exc

    def plan_json(self, prompt: str, schema: dict) -> dict:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt + "\n只輸出 JSON，不要其他文字。"}],
                   "temperature": 0.1, "max_tokens": 800}
        with self._request(payload) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return parse_model_json(content)

    def stream(self, messages: list[dict]):
        payload = {"model": self.model, "messages": messages, "stream": True, "temperature": 0.3, "max_tokens": 2000}
        with self._request(payload, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                text = ((event.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                if text:
                    yield text

    def complete(self, prompt: str, max_tokens: int = 50) -> str:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens}
        with self._request(payload, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""

    def list_models(self) -> list[str]:
        req = urllib.request.Request(self.base_url + "/models", headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _http_error(exc, "") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise OllamaUnavailable(f"連不到 {self.name}。請確認網路或服務有開啟、網址正確。") from exc
        ids = [str(m.get("id") or "") for m in (data.get("data") or data.get("models") or []) if isinstance(m, dict)]
        return sorted({i.removeprefix("models/") for i in ids if i})


def _http_error(exc: urllib.error.HTTPError, model: str) -> RuntimeError:
    body = exc.read().decode("utf-8", "ignore")[:200]
    if exc.code in (401, 403):
        return RuntimeError("API 金鑰不對或沒有權限。請到設定 → AI 助理檢查。")
    if exc.code == 404:
        return RuntimeError(f"找不到這個服務或模型（{model}）。請檢查網址與模型名稱。" if model else "找不到這個服務。請檢查網址。")
    if exc.code == 429:
        return RuntimeError("這個服務暫時拒絕更多請求（用量或額度到了）。請稍後再試，或到服務的網站查看額度。")
    return RuntimeError(f"服務回應 {exc.code}：{body}")


# ---- Claude（Anthropic 官方 Python 套件） ----

class ClaudeLLM:
    """Claude 的原生 Messages API。規劃用低思考強度（快、便宜），回答用中等。
    Opus 與 Sonnet 開啟 Anthropic 的伺服器端備援：模型拒絕回答時，Anthropic 會自動改用其他模型重試。"""

    def __init__(self, model: str, key: str, client=None):
        self.model, self.key = model or CLAUDE_DEFAULT, key
        self.remote = True
        self.name = "Claude"
        self._client = client

    def client(self):
        if self._client is None:
            import anthropic

            if not self.key:
                raise RuntimeError("還沒填 Claude 的 API 金鑰。請到設定 → AI 助理填寫。")
            self._client = anthropic.Anthropic(api_key=self.key, max_retries=2, timeout=300)
        return self._client

    def _extra(self) -> dict:
        if self.model in CLAUDE_FALLBACK_MODELS:
            return {"betas": [CLAUDE_FALLBACK_BETA], "fallbacks": "default"}
        return {}

    @staticmethod
    def _split(messages: list[dict]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
        rest = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")]
        return system, rest

    def _create(self, effort: str, max_tokens: int, messages: list[dict], system: str = ""):
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": messages,
                  "output_config": {"effort": effort}, **self._extra()}
        if system:
            kwargs["system"] = system
        with _claude_errors(self.model):
            if kwargs.get("betas"):
                resp = self.client().beta.messages.create(**kwargs)
            else:
                resp = self.client().messages.create(**kwargs)
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude 拒絕回答這個問題。可以換個說法再問一次。")
        return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")

    def plan_json(self, prompt: str, schema: dict) -> dict:
        return parse_model_json(self._create("low", 16000, [{"role": "user", "content": prompt + "\n只輸出 JSON，不要其他文字。"}]))

    def stream(self, messages: list[dict]):
        system, rest = self._split(messages)
        kwargs = {"model": self.model, "max_tokens": 64000, "messages": rest, "output_config": {"effort": "medium"}, **self._extra()}
        if system:
            kwargs["system"] = system
        with _claude_errors(self.model):
            api = self.client().beta.messages if kwargs.get("betas") else self.client().messages
            with api.stream(**kwargs) as s:
                for text in s.text_stream:
                    if text:
                        yield text
                final = s.get_final_message()
        if final.stop_reason == "refusal":
            raise RuntimeError("Claude 拒絕回答這個問題。可以換個說法再問一次。")

    def complete(self, prompt: str, max_tokens: int = 50) -> str:
        return self._create("low", 2000, [{"role": "user", "content": prompt}])

    def list_models(self) -> list[str]:
        with _claude_errors(""):
            return [m.id for m in self.client().models.list(limit=100)]


class _claude_errors:
    """把 Anthropic 套件的錯誤換成一般人看得懂的話。"""

    def __init__(self, model: str):
        self.model = model

    def __enter__(self):
        return self

    def __exit__(self, kind, exc, tb):
        if exc is None:
            return False
        try:
            import anthropic
        except ImportError:  # pragma: no cover
            return False
        if isinstance(exc, anthropic.AuthenticationError):
            raise RuntimeError("Claude 的 API 金鑰不對。請到設定 → AI 助理重新填寫。") from exc
        if isinstance(exc, anthropic.PermissionDeniedError):
            raise RuntimeError("這把 API 金鑰沒有使用這個模型的權限。") from exc
        if isinstance(exc, anthropic.NotFoundError):
            raise RuntimeError(f"Claude 找不到這個模型（{self.model}）。請到設定 → AI 助理換一個。") from exc
        if isinstance(exc, anthropic.RateLimitError):
            raise RuntimeError("Claude 暫時拒絕更多請求（用量或額度到了）。請稍後再試。") from exc
        if isinstance(exc, anthropic.APIConnectionError):
            raise OllamaUnavailable("連不到 Claude。請確認這台電腦有連上網路。") from exc
        if isinstance(exc, anthropic.APIStatusError):
            raise RuntimeError(f"Claude 回應 {exc.status_code}：{str(exc)[:200]}") from exc
        return False


def make_llm(cfg, client):
    """依設定選擇服務。"""
    p = provider_of(cfg)
    if p == "ollama":
        from .models import assistant_model

        return OllamaLLM(client, cfg.ollama_url, assistant_model(cfg))
    s = api_settings(cfg, p)
    if p == "claude":
        return ClaudeLLM(s["model"], s["key"])
    names = {"gemini": "Gemini", "openai": "OpenAI"}
    return OpenAILLM(s["url"], s["model"], s["key"], names.get(p, ""))


def list_models(cfg, provider: str) -> list[str]:
    """向服務取得可以用的模型（使用者按下按鈕時才連線）。"""
    s = api_settings(cfg, provider)
    if provider == "claude":
        return ClaudeLLM(s["model"], s["key"]).list_models()
    if not s["url"]:
        raise RuntimeError("請先填服務網址。")
    return OpenAILLM(s["url"], s["model"], s["key"]).list_models()


__all__ = ["PROVIDERS", "CLAUDE_MODELS", "CLAUDE_DEFAULT", "KEY_SETTINGS", "MODEL_SETTINGS", "OllamaLLM", "OpenAILLM",
           "ClaudeLLM", "make_llm", "list_models", "provider_of", "api_settings", "is_local_url", "is_remote"]
