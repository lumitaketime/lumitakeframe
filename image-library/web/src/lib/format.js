const WEEK = ["日", "一", "二", "三", "四", "五", "六"];

export function parseLocal(iso) {
  if (!iso) return null;
  const [d, t = "00:00:00"] = iso.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const [hh, mm, ss] = t.split(":").map(Number);
  return new Date(y, (m || 1) - 1, day || 1, hh || 0, mm || 0, ss || 0);
}

export function monthLabel(month) {
  if (!month || month === "0000-00") return "日期不明";
  const [y, m] = month.split("-");
  return `${y}年${Number(m)}月`;
}

export function dayLabel(iso) {
  const d = parseLocal(iso);
  if (!d) return "日期不明";
  // 月份標題已有年份，日期只顯示月日
  return `${d.getMonth() + 1}月${d.getDate()}日 週${WEEK[d.getDay()]}`;
}

export function dateTime(iso, tz) {
  const d = parseLocal(iso);
  if (!d) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 週${WEEK[d.getDay()]} ${pad(d.getHours())}:${pad(d.getMinutes())}${tz ? ` (UTC${tz})` : ""}`;
}

export function duration(sec) {
  if (!sec && sec !== 0) return "";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}

export function bytes(n) {
  if (!n) return "";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}

export function shutter(t) {
  if (!t) return "";
  if (t >= 1) return `${Math.round(t * 10) / 10}″`;
  return `1/${Math.round(1 / t)}`;
}

export function count(n) {
  return new Intl.NumberFormat("zh-TW").format(n || 0);
}

export const LABEL_COLORS = {
  red: "#e5484d",
  yellow: "#f5c518",
  green: "#30a46c",
  blue: "#3e63dd",
  purple: "#8e4ec6",
};
export const LABEL_NAMES = { red: "紅", yellow: "黃", green: "綠", blue: "藍", purple: "紫" };
export const LABEL_KEYS = ["red", "yellow", "green", "blue", "purple"];
