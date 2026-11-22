/**
 * 中文、日文輸入法（注音、倉頡、拼音…）選字時按的 Enter 是「確認選字」，不是「送出」。
 * 瀏覽器通常用 e.isComposing 表示正在選字，但 Mac App 用的 Safari 引擎在確認選字的那一下回報 false、
 * 改用 keyCode 229；有些情況則是先結束選字、緊接著才送出 Enter。三種情況都當成選字，不當成送出。
 */
let lastEnd = 0;
if (typeof document !== "undefined") {
  document.addEventListener("compositionend", () => (lastEnd = Date.now()), true);
}

/** 這一下 Enter 是不是在確認輸入法的選字（是的話不要送出） */
export function composing(e) {
  return !!(e?.isComposing || e?.keyCode === 229 || Date.now() - lastEnd < 80);
}

/** 真正要送出的 Enter（不是選字、沒有按 Shift） */
export function submitEnter(e, { shift = false } = {}) {
  return e.key === "Enter" && !composing(e) && (shift || !e.shiftKey);
}
