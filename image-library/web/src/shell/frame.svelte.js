/**
 * 視窗外框的狀態：側邊欄、資訊欄的開關與寬度，以及「目前這一頁」交給外框顯示的資料
 * （路徑列、狀態列、資訊欄）。頁面用 setFrame() 交出資料，外框只顯示屬於目前網址的那一份。
 */
import { route } from "../lib/router.svelte.js";

export const SIDEBAR_MIN = 200;
export const SIDEBAR_MAX = 320;
/** 視窗小於這個寬度：資訊欄自動收起 */
export const INFO_BREAK = 1100;
/** 視窗小於這個寬度：側邊欄收成抽屜，工具列出現 ≡ */
export const DRAWER_BREAK = 800;

function read(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}
function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 只影響這次 */
  }
}

export const frame = $state({
  sidebar: read("frame.sidebar", true), // 電腦版側邊欄是否顯示（⌘⌃S）
  sidebarWidth: Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, read("frame.sidebarWidth", 240))),
  info: read("frame.info", false), // 資訊欄是否打開（⌘I）
  drawer: false, // 窄視窗時滑出的側邊欄
  page: null, // { key, crumbs, status, location, info }
});

export function toggleSidebar() {
  frame.sidebar = !frame.sidebar;
  save("frame.sidebar", frame.sidebar);
}
export function setSidebarWidth(px) {
  frame.sidebarWidth = Math.round(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, px)));
  save("frame.sidebarWidth", frame.sidebarWidth);
}
export function toggleInfo() {
  frame.info = !frame.info;
  save("frame.info", frame.info);
}

const here = () => route.path + (route.query.path ? `?path=${route.query.path}` : "");

/**
 * 頁面交給外框的資料：
 * crumbs：[{label, href}] 路徑列；status：狀態列左邊的文字；
 * location：{name, online} 目前位置所在的硬碟；info：{title, kind, rows: [[標籤, 值]], kinds} 資訊欄。
 */
export function setFrame(data) {
  frame.page = { key: here(), ...data };
}
/** 目前網址的頁面資料；頁面還沒交出來（或是別頁留下的）就回傳 null */
export function pageFrame() {
  return frame.page && frame.page.key === here() ? frame.page : null;
}
