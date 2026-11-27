/** 待辦：所有等你決定的事（硬碟狀況、計畫卡、分類請你確認、待刪除、提醒） */
import { api } from "../lib/api.js";

export const loadInbox = () => api("/api/inbox", { quiet: true });
export const snoozeReminder = (key, days = 7) => api("/api/reminders/snooze", { body: { key, days } });
