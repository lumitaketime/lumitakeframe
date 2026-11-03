/** 整理工具清單：工具頁的卡片與側邊欄的「常用工具」共用。 */
import { mdiBlur, mdiBrightness6, mdiCellphoneScreenshot, mdiChartBoxOutline, mdiContentDuplicate } from "./icons.js";

export const TOOLS = [
  { key: "blurry", href: "/tools/blurry", label: "模糊照片", icon: mdiBlur },
  { key: "exposure", href: "/tools/exposure", label: "曝光問題", icon: mdiBrightness6 },
  { key: "screens", href: "/tools/screens", label: "截圖與文件", icon: mdiCellphoneScreenshot },
  { key: "large", href: "/tools/large", label: "大檔案", icon: mdiChartBoxOutline },
  { key: "duplicates", href: "/duplicates", label: "重複照片", icon: mdiContentDuplicate },
];

export const toolByKey = (key) => TOOLS.find((t) => t.key === key);

export function pinnedKeys(server) {
  return (server?.ui?.pinned_tools || "").split(",").filter((k) => toolByKey(k));
}
