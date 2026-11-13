核取方塊（macOS）：開、關，或「混合」——父層底下的子項目狀態不一致時。

**使用者提供**：`checked`（`true`／`false`／`'mixed'`）、`onChange`、`label`、`disabled`。

- 用於一組有階層的設定：靠前緣對齊，附屬項目縮排。
- 父層的子項目狀態不同時顯示混合狀態（橫線）。
- 單一開關設定用核取方塊；多個互斥選項改用 RadioGroup；不要用 switch 取代核取方塊。
- 放在視窗內容區，不放工具列或視窗邊框。
- iOS 沒有核取方塊：列表中以勾號（`ListRow accessory="checkmark"`）表示選取。
