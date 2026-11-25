/**
 * 資料層：檔案管理助理。預設只在這台電腦上（Re'memor 的引擎 → 本機的 Ollama）；使用者選了雲端服務時才會送到那個服務。
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
export function ask({ question, history, context, lang, chatId }, onEvent) {
  const ctrl = new AbortController();
  (async () => {
    try {
      const res = await fetch("/api/assistant/ask", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", signal: ctrl.signal,
        body: JSON.stringify({ question, history, context, lang, chat_id: chatId || undefined }),
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

// ---- 助理提出的動作（提案 → 本人確認 → 執行；都可以復原） ----
/** 執行一個提案。only＝只做勾選的項目（索引）。只有使用者在畫面上確認後才呼叫。 */
export const runAction = (id, only) => api("/api/assistant/actions/run", { body: { id, only, confirm: true } });
/** 復原做過的動作 */
export const undoAction = (id) => api("/api/assistant/actions/undo", { body: { id, confirm: true } });
/** 不要這個提案 */
export const dismissAction = (id) => api("/api/assistant/actions/dismiss", { body: { id } });
/** 助理做過的動作（最近的在前） */
export const loadActions = (limit = 30) => api(`/api/assistant/actions?limit=${limit}`, { quiet: true });
/** 向雲端服務取得可以用的模型（使用者按下按鈕才連線，只送金鑰） */
export const loadProviderModels = (provider) => api("/api/assistant/models", { body: { provider } });

// ---- 對話紀錄（只存在這台電腦） ----
/** 所有對話（最近的在前） */
export const loadChats = () => api("/api/assistant/chats", { quiet: true });
/** 一段對話的內容：問題、回答、查詢步驟、找到的來源、提出的動作 */
export const loadChat = (id) => api(`/api/assistant/chats/${id}`);
/** 刪除對話紀錄（可以一次好幾段；不動任何檔案） */
export const deleteChats = (ids) => api("/api/assistant/chats/delete", { body: { ids } });
/** 一個動作現在的狀態（例如背景複製做完了沒） */
export const loadAction = (id) => api(`/api/assistant/actions/${id}`, { quiet: true });
