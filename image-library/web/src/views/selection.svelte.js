/**
 * 選取（五種檢視共用）：按一下單選、⌘ 加按多選、⇧ 加按連續選取；方向鍵移動、⇧ 加方向鍵延伸。
 * 以「第幾個」記錄，所以還沒讀到的項目也能被連續選取；換了排序或位置就要 clear()。
 */
import { SvelteSet } from "svelte/reactivity";

export function createSelection() {
  const picked = new SvelteSet();
  const s = $state({ anchor: -1, focus: -1 });

  function range(a, b) {
    picked.clear();
    for (let i = Math.min(a, b); i <= Math.max(a, b); i++) picked.add(i);
  }
  return {
    picked,
    get focus() { return s.focus; },
    get size() { return picked.size; },
    has: (i) => picked.has(i),
    /** 目前選取的第幾個（由小到大） */
    indexes: () => [...picked].sort((a, b) => a - b),
    clear() {
      picked.clear();
      s.anchor = s.focus = -1;
    },
    click(i, e) {
      if (e?.shiftKey && s.anchor >= 0) range(s.anchor, i);
      else if (e?.metaKey || e?.ctrlKey) {
        picked.has(i) ? picked.delete(i) : picked.add(i);
        s.anchor = i;
      } else {
        picked.clear();
        picked.add(i);
        s.anchor = i;
      }
      s.focus = i;
    },
    /** 右鍵：按在已選取的項目上就維持選取，否則改選這一個 */
    context(i) {
      if (!picked.has(i)) this.click(i);
    },
    /** 鍵盤移動到第 i 個；extend＝按著 ⇧ */
    moveTo(i, total, extend = false) {
      if (!total) return;
      i = Math.max(0, Math.min(total - 1, i));
      if (extend && s.anchor >= 0) range(s.anchor, i);
      else {
        picked.clear();
        picked.add(i);
        s.anchor = i;
      }
      s.focus = i;
    },
    all(total) {
      range(0, total - 1);
      s.anchor = 0;
      s.focus = Math.max(0, s.focus);
    },
  };
}
