/**
 * 介面語言：文字放在語言檔（每種語言一個檔案），程式裡用 t("鍵名") 取用，不直接寫中文。
 * 數量、大小、日期用語系格式化，不用字串拼接。預設提供繁體中文與英文；其他語言之後以語言包加入。
 */
import zhHant from "./zh-Hant.js";
import en from "./en.js";

const PACKS = { "zh-Hant": zhHant, en };
export const LOCALES = [
  { id: "zh-Hant", label: "繁體中文", intl: "zh-TW" },
  { id: "en", label: "English", intl: "en-US" },
];

function detect() {
  try {
    const saved = localStorage.getItem("locale");
    if (saved && PACKS[saved]) return saved;
  } catch {
    /* 無法使用 localStorage 時依瀏覽器語言 */
  }
  const langs = typeof navigator !== "undefined" ? navigator.languages || [navigator.language] : [];
  for (const l of langs) {
    if (/^zh/i.test(l)) return "zh-Hant";
    if (/^en/i.test(l)) return "en";
  }
  return "zh-Hant";
}

export const i18n = $state({ locale: detect() });

export function setLocale(id) {
  if (!PACKS[id]) return;
  i18n.locale = id;
  try {
    localStorage.setItem("locale", id);
  } catch {
    /* 只影響這次 */
  }
  if (typeof document !== "undefined") document.documentElement.lang = id;
}

const intlTag = () => LOCALES.find((l) => l.id === i18n.locale)?.intl || "zh-TW";

/** 取介面文字；找不到時退回繁體中文，再找不到就顯示鍵名（方便發現漏掉的字）。 */
export function t(key, params) {
  const text = PACKS[i18n.locale]?.[key] ?? zhHant[key] ?? key;
  return params ? text.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : text;
}

/** 數量：1,284 */
export function formatNumber(n, options) {
  return new Intl.NumberFormat(intlTag(), options).format(n || 0);
}

/** 大小：KB、MB、GB、TB，最多一位小數 */
export function formatBytes(n) {
  if (!n) return "";
  const units = [["TB", 1e12], ["GB", 1e9], ["MB", 1e6]];
  for (const [unit, size] of units) {
    if (n >= size) return `${formatNumber(n / size, { maximumFractionDigits: 1 })} ${unit}`;
  }
  return `${formatNumber(Math.max(1, Math.round(n / 1e3)))} KB`;
}

/** 日期：2026/11/10（依語系）；date 可以是 Date 或秒數 */
export function formatDate(date) {
  const d = date instanceof Date ? date : new Date(date * 1000);
  if (isNaN(d)) return "";
  return new Intl.DateTimeFormat(intlTag(), { year: "numeric", month: "numeric", day: "numeric" }).format(d);
}

/** 日期與時間：2026/11/10 週二 14:20 */
export function formatDateTime(date) {
  const d = date instanceof Date ? date : new Date(date * 1000);
  if (isNaN(d)) return "";
  const tag = intlTag();
  const day = new Intl.DateTimeFormat(tag, { weekday: "short" }).format(d);
  const time = new Intl.DateTimeFormat(tag, { hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
  return `${formatDate(d)} ${day} ${time}`;
}
