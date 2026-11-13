開關（switch）在兩個相反狀態間切換：開或關。

**使用者提供**：`checked`／`defaultChecked`、`onChange`、`label`（或 `aria-label`）、`size`（`regular`／`mini`，mini 只用於 macOS）、`disabled`。

## 規則（HIG Toggles）
- 讓開、關的差異一目了然，**不要只靠顏色**——本元件以圓鈕位置表達狀態。
- 清楚標示開關影響的對象。
- **iOS／iPadOS：只在列表列中使用 switch**（放在 `ListRow` 的 `accessory`）；列表以外改用切換式按鈕。保留預設綠色（`toggle-on`），除非需要改成強調色。
- **macOS**：switch、核取方塊、選項按鈕放在視窗內容區，不放在視窗邊框或工具列。強調的設定用 switch；群組表單中單一列可用 mini switch；主要設定用 regular、附屬設定用 mini。不要用 switch 取代核取方塊。
- 按住時圓鈕轉為 Liquid Glass（HIG：滑桿、開關這類短暫控制項在操作中呈現玻璃）。

## 尺寸（本系統取值）
iOS 51×31pt（命中區域補足 44pt）；macOS regular 38×22、mini 26×15。
