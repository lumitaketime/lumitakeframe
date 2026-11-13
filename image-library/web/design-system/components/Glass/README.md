Liquid Glass 是浮在內容之上的功能層材質，用在控制項與導覽元素——絕不用在內容層。

**使用者提供**：`variant`（`regular` 預設／`clear`）、`shape`（`capsule`、`rounded`、`rect`、`circle`）、`dim`（clear 時加 35% 調暗層）、`interactive`（按壓回饋）、子元素。

## 何時用哪一種
- **regular**：大多數系統元件使用；會模糊並調整亮度以確保可讀。文字多的元件（Alert、側邊欄、Popover）一律用 regular。
- **clear**：高度透明，**只**用在照片、影片等視覺豐富的背景之上；底下內容明亮時加 `dim`——數值來自 HIG：「consider adding a dark dimming layer of 35% opacity」（`glass-dim`）。

## 規則（HIG Materials、Color）
- 少用：標準元件已自動帶玻璃；自訂元件只把玻璃留給最重要的功能元素。
- 不在內容層使用玻璃；內容層的背景用標準材質（ultraThin、thin、regular、thick）。
- 玻璃本身沒有顏色，取用背後內容的色彩。要強調主要動作時，替**背景**上色（`Button variant="glassProminent"`），不要替符號或文字上色；不要讓多個控制項同時上色。
- 其上文字用 `label-primary`；次要文字用 `label-glass-secondary`（不用 `label-secondary`）。
- 「減少透明度」與增強對比時，玻璃會變得接近不透明（本系統已在增強對比主題與 `prefers-reduced-transparency` 處理）。

## 網頁近似
CSS 以 `glass-regular`／`glass-clear` 填色 + `blur-glass` 背景模糊 + `shadow-rim` 邊緣高光模擬；折射與鏡面反光無法在網頁重現。原生 App 請用 SwiftUI `glassEffect(_:in:)`，不要自行模仿。
