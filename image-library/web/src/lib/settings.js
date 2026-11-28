/**
 * 設定的分類、舊網址的對應，以及「搜尋設定」用的索引。
 * 設定頁（pages/Settings.svelte）、設定的側邊欄（shell/SettingsSidebar.svelte）、工具列的標題都用這一份。
 * 索引只記語言檔的鍵，顯示時再翻譯，所以中英文都搜得到。
 */

export const CATS = [
  { id: "general", icon: "gear", tint: "gray-1" },
  { id: "catalog", icon: "external-drive-fill", tint: "blue" },
  { id: "scan", icon: "clock", tint: "orange" },
  { id: "text", icon: "magnifyingglass", tint: "indigo" },
  { id: "assistant", icon: "sparkles", tint: "purple" },
  { id: "classify", icon: "tag", tint: "green" },
  { id: "photos", icon: "photo", tint: "pink" },
  { id: "system", icon: "slider-horizontal", tint: "gray-1" },
  { id: "about", icon: "info", tint: "gray-1" },
];

/** 舊網址（照片圖庫的設定分類）對到新的分類與子分類 */
export const OLD = {
  ai: ["photos", "ai"], recog: ["photos", "recog"], faces: ["photos", "recog"], search: ["photos", "search"], organize: ["photos", "organize"],
  rating: ["photos", "organize"], tools: ["photos", "organize"], library: ["photos", "library"], look: ["photos", "library"], features: ["photos", "library"],
  phone: ["system", ""], storage: ["system", ""], advanced: ["system", ""], about: ["about", ""],
};

/** 網址的第二段 → 分類 id；認不得就是空字串 */
export function resolveCat(section) {
  if (!section) return "";
  if (CATS.some((c) => c.id === section)) return section;
  return OLD[section]?.[0] || "";
}

// 每個分類裡的段落與項目（語言檔的鍵）。sub＝照片底下的分頁。
const RAW = {
  general: ["set.general.ui", "set.general.language", "set.general.appearance", "set.general.onboarding", "set.general.version", "set.general.start",
    "set.general.startPage", "set.spotlight.title", "set.spotlight.toggle", "set.spotlight.internal", "set.spotlight.rebuild"],
  catalog: ["set.catalog.size", "set.catalog.db", "set.catalog.textIndex", "set.catalog.thumbs", "set.catalog.skip", "set.catalog.skipHidden",
    "set.catalog.skipSystem", "set.catalog.skipLibrary", "set.catalog.skipNoindex", "set.catalog.drives", "set.catalog.folder", "set.catalog.change",
    "set.backup.title", "set.backup.dir", "set.backup.auto", "set.backup.keep", "set.backup.now", "set.backup.clean", "set.backup.reset"],
  scan: ["set.scan.promise", "set.scan.readOnly", "set.scan.resume", "set.scan.when", "set.scan.onStart", "set.scan.autoContinue", "set.scan.parallel",
    "set.scan.autoText", "set.scan.awake", "set.scan.manual", "set.scan.compare", "set.scan.log"],
  text: ["set.lang.title", "set.lang.builtin", "set.text.status", "set.text.cloud", "set.text.indexSize", "set.text.formats", "set.ocr.title",
    "set.ocr.languages", "set.text.reset", "set.sem.title", "set.sem.toggle"],
  assistant: ["set.ai.where", "set.ai.machine", "set.ai.model", "set.ai.apiSettings", "set.ai.perm", "set.ai.history", "oll.install", "oll.update"],
  classify: ["cat.set.list", "cat.set.add", "cat.set.restore", "cat.look.title", "cat.set.title", "cat.choice.rules_auto", "cat.choice.ai_auto",
    "cat.choice.read_text", "cat.set.cloud", "rule.title", "prof.title"],
  system: ["phone.title", "phone.allow"],
};
const PHOTO = { ai: ["set.photos.ai", "cmp.title"], recog: ["set.photos.recog"], search: ["set.photos.search"], organize: ["set.photos.organize"], library: ["set.photos.library"] };

export const INDEX = [
  ...Object.entries(RAW).flatMap(([cat, keys]) => keys.map((key) => ({ cat, sub: "", key }))),
  ...Object.entries(PHOTO).flatMap(([sub, keys]) => keys.map((key) => ({ cat: "photos", sub, key }))),
];

/** 搜尋設定：分類名稱或項目名稱含有查詢字（不分大小寫）。t＝翻譯函式 */
export function searchSettings(query, t, limit = 30) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out = [];
  const seen = new Set();
  for (const c of CATS) {
    const label = t(`set.cat.${c.id}`);
    if (label.toLowerCase().includes(q)) {
      out.push({ cat: c.id, sub: "", label, pane: label, whole: true });
      seen.add(label);
    }
  }
  for (const e of INDEX) {
    const label = t(e.key);
    if (!label || label === e.key || label.includes("{") || seen.has(label) || !label.toLowerCase().includes(q)) continue;
    seen.add(label);
    out.push({ ...e, label, pane: t(`set.cat.${e.cat}`) + (e.sub ? ` › ${t(`set.photos.${e.sub}`)}` : "") });
    if (out.length >= limit) break;
  }
  return out;
}
