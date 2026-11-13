Sheet 承載與目前情境密切相關、範圍明確的任務，例如要求輸入資訊或選擇儲存位置。

**使用者提供**：`title`、`detent`（iOS：`medium`／`large`）、`grabber`、`cancelLabel`／`doneLabel`、`onCancel`／`onDone`、`doneDisabled`、`hideDone`、`symbols`（iOS 以 xmark／checkmark 玻璃按鈕呈現，預設 true）、`height`、子元素。

## 規則（HIG Sheets）
- 一次只顯示一個 Sheet；要顯示第二個前先關閉第一個。
- 有「完成」就一定配「取消」（多步驟流程則配「返回」）；不要同時出現取消、完成、返回三者。
- iOS 單頁 Sheet：取消在頂端工具列前緣、完成在後緣。多步驟：第一步取消＋停用的完成，之後以返回取代取消，最後一步完成可按。
- 支援向下滑動關閉；有未儲存的變更時用 ActionSheet 確認。
- iPhone 可支援 medium 段位（約全高的一半）做漸進揭露；撰寫類 Sheet 保持全高。可調整大小的 Sheet 要有抓取把手。
- iPadOS 使用 page sheet 或 form sheet 樣式。
- macOS：Sheet 附著在視窗上、使父視窗變暗；給合理的預設大小；需要反覆輸入並查看結果時改用面板（panel）。按鈕在右下：取消、主要動作在最後緣。
- 複雜或冗長的流程改用全螢幕模態（iOS）或新視窗（macOS）。

本元件 iOS 的 medium 段位以玻璃呈現、large 段位為不透明 `elevated-primary`。
