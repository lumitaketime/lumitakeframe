/**
 * 佔比圖（方塊圖與環狀圖共用）的資料整理：把引擎回傳的兩層資料攤平成「可以選取的單位」，
 * 每個單位長得像一般的項目（有 type、name、size…），所以選取、右鍵選單、快速預覽都能共用。
 */

/** 上色用的類型：資料夾用它裡面佔最多空間的類型（引擎在掃描完時算好），沒有資料時才用資料夾的黃色 */
export const colorKey = (unit) => (unit.type === "folder" ? unit.mainKind || "folder" : unit.rest ? "rest" : unit.kind);

export function buildUnits(usage, rootId, t, formatNumber) {
  const units = [];
  const tops = [];
  const toUnit = (b, parent) => {
    if (b.type === "folder") return { type: "folder", id: b.id, name: b.name, path: b.path, root_id: rootId, size: b.bytes, files: b.files, kind: "folder", mainKind: b.kind };
    if (b.type === "kind") {
      return { type: "group", kind: b.kind, name: t(`kind.${b.kind}`), kindLabel: t("usage.filesHere"), path: b.path, root_id: rootId, size: b.bytes, files: b.files,
        note: parent ? parent.name : "" };
    }
    return { type: "group", rest: true, kind: "other", name: t("usage.rest", { count: formatNumber(b.count) }), kindLabel: t("usage.restKind"),
      path: parent ? parent.path : usage.path, root_id: rootId, size: b.bytes, files: b.files };
  };
  for (const b of usage?.children || []) {
    const unit = toUnit(b, null);
    const top = { unit, index: units.length, children: [] };
    units.push(unit);
    for (const c of b.children || []) {
      top.children.push({ unit: toUnit(c, b), index: units.length });
      units.push(top.children[top.children.length - 1].unit);
    }
    tops.push(top);
  }
  return { units, tops };
}
