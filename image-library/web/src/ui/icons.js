/**
 * 介面圖示：設計系統的 28 個圖示（24×24 格線、圓角端點），加上 Re'memor 需要而設計系統沒有的。
 * 補畫的圖示放在 EXTRA，規格相同；每一步需要時再加。
 */
import { ICONS as BASE } from "../../design-system/components/src/icons.js";

const EXTRA = {
  "video": '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="M16 10.5l5-3v9l-5-3"/>',
  "document": '<path d="M6.5 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5z"/><path d="M13.5 3.5v4h4M8.5 12.5h7M8.5 16h5"/>',
  "archive": '<rect x="5" y="3.5" width="14" height="17" rx="2.5"/><path d="M12 3.5v2M12 7.5v2M12 11.5v1.5"/><rect x="10.5" y="13" width="3" height="4" rx="1"/>',
  "duplicate": '<rect x="8.5" y="8.5" width="12" height="12" rx="2.5"/><path d="M15.5 8.5V6a2.5 2.5 0 0 0-2.5-2.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5"/>',
  "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8"/>',
  "list": '<path d="M8.5 6.5h11M8.5 12h11M8.5 17.5h11"/><circle cx="4.7" cy="6.5" r="1" fill="currentColor" stroke="none"/><circle cx="4.7" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="4.7" cy="17.5" r="1" fill="currentColor" stroke="none"/>',
  "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
  "columns": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M9.2 4.5v15M14.8 4.5v15"/>',
  "tree": '<path d="M5 5.5h6M5 5.5v13h4M5 12h4M13 12h6M13 18.5h6"/>',
  "treemap": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M12.5 4.5v15M12.5 11h8M3.5 13.5h9"/>',
};

export const ICONS = { ...BASE, ...EXTRA };
export const iconNames = Object.keys(ICONS);
