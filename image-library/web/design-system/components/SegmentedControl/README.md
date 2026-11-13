分段控制：一列等寬的分段，每段是一個按鈕，用來切換緊密相關的檢視或選項。

**使用者提供**：`segments`（`{value, label}` 或 `{value, icon, ariaLabel}`）、`value`／`defaultValue`、`onChange`、`momentary`（動作按鈕組，無選取狀態）、`fullWidth`、`ariaLabel`。

## 規則（HIG Segmented controls）
- 段寬一致；每段內容大小相近。
- 同一個控制項裡只用文字或只用圖示，**不要混用**。
- 標籤用名詞或名詞片語；有文字標籤時不需要引導文字。
- 不要在選擇型控制項中混入動作，反之亦然（動作型請用 `momentary`）。
- 段數：寬版面約五到七段；**iPhone 不超過約五段**。
- iOS 中要切換 App 的不同區塊時用 Tab bar，不用分段控制。
- macOS：純圖示分段要在下方加標籤或提供工具提示；適合放在工具列或檢查器。watchOS 不支援。
