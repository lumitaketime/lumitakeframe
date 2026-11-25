/**
 * 顯示用的名稱：網頁下載的檔名常常是「%E5%85%A7…」這種編碼過的樣子，還原成看得懂的字。
 * 只改畫面上顯示的，不改硬碟上的名稱（和引擎 classify.pretty_name 一樣的規則）。
 */
export function prettyName(name) {
  const s = String(name ?? "");
  if ((s.match(/%[0-9A-Fa-f]{2}/g) || []).length < 2) return s;
  try {
    const out = decodeURIComponent(s);
    return out || s;
  } catch {
    return s;
  }
}

/** 硬碟格式的名稱：引擎看不出格式時回傳「未知」，換成目前語言的說法 */
export function fsName(label, t) {
  return label === "未知" ? t("drive.fsUnknown") : label || "";
}
