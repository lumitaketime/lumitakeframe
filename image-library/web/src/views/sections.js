/**
 * 分組（像 Finder 的「分組方式」）：把引擎回傳的「每組幾個」換成清單裡的一段一段。
 * 引擎的順序是：資料夾（自成一組）→ 依組別排好的檔案，所以每一段的開頭位置就是前面各組數量的累加。
 */

/** 組別鍵（「排序前綴:名稱」）換成標題 */
export function groupLabel(group, key, t) {
  const parts = key.split(":");
  const name = parts[parts.length - 1];
  if (group === "kind") return t(`kind.${name}`);
  if (group === "label") return name === "none" ? t("label.none") : t(`label.${name}`);
  if (group === "size") return t(`group.size.${name}`);
  if (group === "name") return name || "—";
  if (["today", "week", "month", "unknown"].includes(name)) return t(`group.date.${name}`);
  return t("group.year", { year: name });
}

/** {folders, groups: [{key, count}]} → [{key, label, start, count}] */
export function buildSections(data, group, t) {
  if (!data) return null;
  const out = [];
  let start = 0;
  if (data.folders) {
    out.push({ key: "folders", label: t("info.kind.folder"), start, count: data.folders });
    start += data.folders;
  }
  for (const g of data.groups) {
    out.push({ key: g.key, label: groupLabel(group, g.key, t), start, count: g.count });
    start += g.count;
  }
  return out;
}

/** 第 i 個項目在哪一段（二分搜尋） */
export function sectionOf(sections, i) {
  let lo = 0, hi = sections.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (sections[mid].start <= i) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/**
 * 列表的版面：每一段前面多一列標題。第 k 段的標題在第 start+k 列，段內第 i 個項目在第 i+k+1 列。
 * 沒有分組時就是「第 i 列＝第 i 個項目」。
 */
export function listLayout(sections, total) {
  if (!sections?.length) return { rows: total, at: (r) => ({ i: r }), rowOf: (i) => i };
  const heads = sections.map((s, k) => s.start + k);
  return {
    rows: total + sections.length,
    at(r) {
      let lo = 0, hi = heads.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (heads[mid] <= r) lo = mid;
        else hi = mid - 1;
      }
      return r === heads[lo] ? { section: sections[lo] } : { i: r - lo - 1 };
    },
    rowOf: (i) => i + sectionOf(sections, i) + 1,
  };
}
