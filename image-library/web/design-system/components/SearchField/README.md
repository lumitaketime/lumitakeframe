搜尋欄：搜尋一組內容；有放大鏡圖示、清除按鈕與佔位文字。

**使用者提供**：`placeholder`（說明可以搜尋什麼）、`value`／`defaultValue`、`onChange`、`onSubmit`、`tokens` + `onRemoveToken`、`scopes` + `scope` + `onScopeChange`、`glass`（浮在內容上時）。

## 規則（HIG Search fields）
- 佔位文字說明可搜尋的內容（「搜尋照片、地點、人物」）。
- 盡量邊打字邊顯示結果；提供最近搜尋或建議詞。
- 最相關的結果排最前，並分類呈現；用範圍列（scope bar）在明確分類間篩選，預設較廣的範圍。
- 搜尋標記（token）把一個篩選條件呈現為可選取、可編輯的單一項目，最好搭配建議使用。
- 位置依版面決定：iOS 可放在 Tab bar 的專屬搜尋分頁（尾端）、工具列（有空間時優先底部），或內嵌在列表上方。
- iPadOS／macOS 分割檢視：放工具列尾端；要篩選側邊欄時放側邊欄頂端。
