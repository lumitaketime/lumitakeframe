/**
 * 佔比圖（方塊圖與環狀圖共用）的資料整理：引擎回傳一棵扁平的樹（每個欄位一個陣列，第 0 個是目前的資料夾），
 * 這裡把它變成「可以選取的單位」：每個子資料夾、每個檔案、每塊「其他」都是一個單位，
 * 長得像一般的項目（有 type、name、size…），所以選取、右鍵選單、快速預覽都能共用。
 */

/** 上色用的類型：資料夾用它裡面佔最多空間的類型（引擎在掃描完時算好），沒有資料時才用資料夾的黃色 */
export const colorKey = (unit) => (unit.type === "folder" ? unit.mainKind || "folder" : unit.rest ? "rest" : unit.kind);

/**
 * 回傳 { units, kids, top, least }：
 * units[i]＝第 i 個單位（引擎第 i+1 個節點）；kids[i]＝它的子單位；top＝目前資料夾底下第一層的單位。
 */
export function buildTree(data, rootId, t, formatNumber) {
  const units = [];
  const kids = [];
  const top = [];
  if (!data) return { units, kids, top, least: 0 };
  const n = data.nodes;
  const count = n.parent.length;
  const paths = new Array(count);
  paths[0] = data.path;
  for (let k = 1; k < count; k++) {
    const parent = n.parent[k];
    const ppath = paths[parent] || "";
    const type = n.type[k];
    let unit;
    if (type === 0) {
      paths[k] = n.path[k];
      unit = { type: "folder", id: n.id[k], name: n.name[k], path: n.path[k], root_id: rootId, size: n.bytes[k], files: n.files[k], kind: "folder",
        mainKind: n.kind[k], folder: ppath };
    } else if (type === 1) {
      paths[k] = ppath ? `${ppath}/${n.name[k]}` : n.name[k];
      unit = { type: "file", id: n.id[k], name: n.name[k], path: paths[k], folder: ppath, root_id: rootId, size: n.bytes[k], kind: n.kind[k] };
    } else {
      paths[k] = ppath;
      unit = { type: "group", rest: true, kind: "other", folderId: n.id[k], below: data.least, count: Number(n.name[k]) || 0,
        name: t("usage.rest", { count: formatNumber(Number(n.name[k]) || 0) }), kindLabel: t("usage.restKind"), path: ppath, root_id: rootId,
        size: n.bytes[k], files: n.files[k] };
    }
    unit.parentUnit = parent - 1; // -1＝目前的資料夾
    unit.depth = n.depth[k];
    units.push(unit);
    kids.push([]);
    if (parent === 0) top.push(k - 1);
    else kids[parent - 1].push(k - 1);
  }
  return { units, kids, top, least: data.least };
}
