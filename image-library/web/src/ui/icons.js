/**
 * 介面圖示：設計系統的 28 個圖示（24×24 格線、圓角端點），加上 Re'memor 需要而設計系統沒有的。
 * 補畫的圖示放在 EXTRA，規格相同；每一步需要時再加。
 */
import { ICONS as BASE } from "../../design-system/components/src/icons.js";

const EXTRA = {
  "chart": '<path d="M4 20.5h16"/><rect x="5.5" y="12" width="3" height="6" rx="1"/><rect x="10.5" y="7" width="3" height="11" rx="1"/><rect x="15.5" y="4" width="3" height="14" rx="1"/>',
  "book": '<path d="M12 6.5C10.3 5.2 7.8 4.5 4.5 4.5v13c3.3 0 5.8.7 7.5 2 1.7-1.3 4.2-2 7.5-2v-13c-3.3 0-5.8.7-7.5 2z"/><path d="M12 6.5v13"/>',
  "briefcase": '<rect x="3.5" y="7.5" width="17" height="12" rx="2"/><path d="M9 7.5V5.5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5.5v2M3.5 12.5h17"/>',
  "airplane": '<path d="M10.5 13.5 4 11l1.5-1.5 6 1L16 6a2 2 0 0 1 2.8 2.8l-4.5 4.5 1 6L13.8 21l-2.5-6.5-3.3 3.3.4 2.2-1.4 1.4-1.6-3.4-3.4-1.6 1.4-1.4 2.2.4z"/>',
  "paintbrush": '<path d="M14.5 4.5 19.5 9.5 12 17l-5-5z"/><path d="M7 12c-2.5 0-3.5 2-3.5 4.5 0 1.5-.5 2.5-1 3 3 .5 6.5 0 7.5-2.5L12 17"/>',
  "tag": '<path d="M3.5 11.5V4.5a1 1 0 0 1 1-1h7l9 9a1.5 1.5 0 0 1 0 2.1l-6.4 6.4a1.5 1.5 0 0 1-2.1 0z"/><circle cx="8" cy="8" r="1.5"/>',
  "pause": '<rect x="7" y="5" width="3.5" height="14" rx="1.2"/><rect x="13.5" y="5" width="3.5" height="14" rx="1.2"/>',
  "video": '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="M16 10.5l5-3v9l-5-3"/>',
  "document": '<path d="M6.5 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5z"/><path d="M13.5 3.5v4h4M8.5 12.5h7M8.5 16h5"/>',
  "archive": '<rect x="5" y="3.5" width="14" height="17" rx="2.5"/><path d="M12 3.5v2M12 7.5v2M12 11.5v1.5"/><rect x="10.5" y="13" width="3" height="4" rx="1"/>',
  "duplicate": '<rect x="8.5" y="8.5" width="12" height="12" rx="2.5"/><path d="M15.5 8.5V6a2.5 2.5 0 0 0-2.5-2.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5"/>',
  "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8"/>',
  "list": '<path d="M8.5 6.5h11M8.5 12h11M8.5 17.5h11"/><circle cx="4.7" cy="6.5" r="1" fill="currentColor" stroke="none"/><circle cx="4.7" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="4.7" cy="17.5" r="1" fill="currentColor" stroke="none"/>',
  "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
  "columns": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M9.2 4.5v15M14.8 4.5v15"/>',
  "tree": '<path d="M5 5.5h6M5 5.5v13h4M5 12h4M13 12h6M13 18.5h6"/>',
  "external-drive-fill": '<path d="M5.2 12L7.6 6h8.8l2.4 6"/><rect x="3" y="12" width="18" height="7" rx="2" fill="currentColor"/>',
  "menu": '<path d="M4.5 7h15M4.5 12h15M4.5 17h15"/>',
  "files": '<rect x="7.5" y="3.5" width="12" height="15" rx="2.5"/><path d="M7.5 6.5H6A1.5 1.5 0 0 0 4.5 8v11A1.5 1.5 0 0 0 6 20.5h8.5A1.5 1.5 0 0 0 16 19v-.5M11 8.5h5M11 12h5"/>',
  "sidebar-right": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M14.5 5v14M17 8.5h1.5M17 11h1.5"/>',
  "file": '<path d="M6.5 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5z"/><path d="M13.5 3.5v4h4"/>',
  "sort-up": '<path d="M7 14.5l5-5 5 5"/>',
  "sort-down": '<path d="M7 9.5l5 5 5-5"/>',
  "sort": '<path d="M7.5 5v14M7.5 19l-3.2-3.2M7.5 19l3.2-3.2M16.5 19V5M16.5 5l-3.2 3.2M16.5 5l3.2 3.2"/>',
  "treemap": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M12.5 4.5v15M12.5 11h8M3.5 13.5h9"/>',
  "sparkles": '<path d="M10 3.5l1.6 4.4 4.4 1.6-4.4 1.6L10 15.5l-1.6-4.4L4 9.5l4.4-1.6z"/><path d="M17.5 13.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
  "arrow-up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
  "arrow-down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
  "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
  "shield": '<path d="M12 3.5 5 6v5.5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9V6z"/><path d="M9 12.2l2.1 2.1L15.2 10"/>',
  "play": '<path d="M8 5.5v13l10-6.5z"/>',
};

export const ICONS = { ...BASE, ...EXTRA };
export const iconNames = Object.keys(ICONS);
