按鈕立即執行一個動作；樣式（variant）、角色（role）、尺寸（size）三者決定它的外觀與行為。

**使用者提供**：`children`（以動詞開頭的標籤）、`variant`、`role`、`size`、`shape`、`icon`／`iconOnly`（純圖示時必須給 `aria-label`）、`loading` + `loadingLabel`、`onClick`、`platform`（通常由 `ContentLayer` 決定）。

## 樣式對照（SwiftUI buttonStyle）
| variant | 用途 |
|---|---|
| `glassProminent` | 浮在內容上的主要動作（工具列「完成」、Sheet 確認） |
| `glass` | 浮在內容上的一般動作（關閉、分享、更多） |
| `borderedProminent` | 內容層中的主要動作（儲存、繼續） |
| `bordered` | 內容層中的一般動作（預設） |
| `borderless` | 低強調的文字動作（了解更多） |

## 規則（HIG Buttons）
- 每個畫面最可能的動作用 prominent 樣式，且**一個畫面最多一到兩個** prominent 按鈕。
- 用樣式而不是尺寸標示偏好選項；同一組按鈕保持同尺寸。
- 角色：`primary`（本系統以 prominent 樣式表示，按 Return 觸發）、`cancel`、`destructive`（系統紅）。**絕不把主要角色給破壞性按鈕。**
- 標籤以動詞開頭、清楚說明結果；macOS 中會開啟另一個視窗或需要更多資訊的按鈕加刪節號「…」。
- 一般偏好膠囊或圓形；獨立按鈕用膠囊。
- 自訂按鈕一定要有按壓狀態。不要用白底黑字的自訂按鈕——系統保留給「已切換」狀態。
- 延遲動作在按鈕內顯示活動指示器，可改標籤（「結帳」→「結帳中…」）。
- 命中範圍：iOS／iPadOS 至少 44×44pt（`target-ios`，本元件以隱形區域補足）；macOS 預設 28×28pt；visionOS 60×60pt。按鈕之間留足空間（有框元素周圍約 12pt）。

## 尺寸（本系統取值）
macOS：mini 20、small 24、regular 28、large 36、extraLarge 44（px／pt）。iOS：mini 24、small 28、regular 36、large 50、extraLarge 56。

## 對比
`on-accent` 白字在標準主題的系統藍上約 3.5:1（Apple 原始配對），未達 17pt 一般字 4.5:1；本元件 prominent 文字用 semibold，並由增強對比主題提供 ≥ 4.5:1 的版本。
