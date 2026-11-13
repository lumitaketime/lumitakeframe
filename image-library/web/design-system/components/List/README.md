列表以列（row）呈現資料，可分群組並有頁首頁尾；`ListRow` 是其中的每一列。

**使用者提供**：`List` —— `appearance`（`insetGrouped`／`plain`）、`header`、`footer`、`alternating`（macOS 交替列色）、`ListRow` 子元素。`ListRow` —— `title`、`subtitle`、`detail`、`icon` + `iconTint`（系統色名稱）、`accessory`（`disclosure`、`checkmark`、`info`，或任何節點例如 `Toggle`）、`selected`、`destructive`、`disabled`、`onClick`／`href`。

## 規則（HIG Lists and tables）
- 以文字為主的資料用列表；尺寸差異大或大量圖片時改用集合（collection）。
- 文字保持簡短以免截斷；兩端都重要時用中間省略。
- 選取回饋：導覽列保持反白以顯示路徑；選項列短暫反白後顯示勾號。
- 展開指示器（`disclosure`）用來進入下一層；資訊按鈕（`info`）只用來顯示該列的更多資訊。
- 多欄表格用描述性的欄名（名詞，不加結尾標點）。
- 群組列表搭配 `ContentLayer tone="grouped"` 與 `grouped-*` 色（HIG Color）。
- macOS：可點欄名排序、再點反向；寬表格可用交替列色；階層資料用大綱視圖。

## 平台
- iOS：列高至少 44pt、17pt 字；有圖示時分隔線從文字起點開始。設定式圖示為 29pt 圓角方塊＋白色符號（`on-media`）——黃、薄荷等淺色底上的白符號對比不足 3:1，請改用較深的系統色。
- macOS：一般列 28pt、13pt 字；表單群組列約 40pt；選取列用 `selection`（強調色）。
