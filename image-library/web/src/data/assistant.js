/**
 * 資料層：檔案管理助理。問題與回答都只在這台電腦上（Re'memor 的引擎 → 本機的 Ollama），不會送到網路上。
 */
import { api } from "../lib/api.js";

/** 助理能不能用：Ollama 有沒有開、模型下載了沒 */
export const loadAssistantStatus = () => api("/api/assistant/status", { quiet: true });
/** 「我可以幫忙什麼」：直接從目錄算出來的建議 */
export const loadSuggestions = () => api("/api/assistant/suggestions", { quiet: true });
/** 下載助理用的模型（使用者按下確認後才呼叫；這是唯一會連到網路的動作） */
export const downloadModel = (model) => api("/api/jobs", { body: { kind: "pull", model } });
/** 打開 Ollama（只在這台 Mac 上） */
export const startOllama = () => api("/api/ollama/start", { body: {} });

/**
 * 問一個問題。onEvent 會依序收到：{type:"step", tool, args}、{type:"token", text}、{type:"done", sources}、{type:"error", message}。
 * 回傳一個可以呼叫來中途停止的函式。
 */
export function ask({ question, history, context, lang }, onEvent) {
  const ctrl = new AbortController();
  (async () => {
    try {
      const res = await fetch("/api/assistant/ask", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", signal: ctrl.signal,
        body: JSON.stringify({ question, history, context, lang }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        onEvent({ type: "error", message: data.detail || data.error || res.statusText });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (line) onEvent(JSON.parse(line));
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") onEvent({ type: "error", message: e.message });
    }
  })();
  return () => ctrl.abort();
}
