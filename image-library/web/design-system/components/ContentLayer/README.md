內容層是 App 自己的內容與背景，位在 Liquid Glass 功能層之下；它也決定子元件用 macOS 或 iOS 的尺寸與字級。

**使用者提供**：`platform`（`mac` 預設／`ios`）、`tone`（`plain` 一般畫面、`grouped` 群組列表、`window` macOS 視窗、`media` 照片影片示意）、子元素。

- 分層原則（HIG Materials）：玻璃只屬於控制項與導覽的功能層；內容層用 `bg-*`、`grouped-*`、`window-bg` 等不透明底色或標準材質。
- 讓滿版背景內容延伸到側邊欄、工具列、Tab bar 之下，鋪滿整個畫面或視窗（HIG Layout）。
- 控制項不要墊實心或半透明色塊，改用捲動邊緣效果（`Toolbar` 的 `edgeEffect`）把控制項從內容中托起。
- `tone="grouped"` 只在群組列表（inset grouped）時使用，其他情況用 `plain`（HIG Color）。
- `tone="media"` 是以系統色色塊模擬照片內容的示意背景，只供預覽與原型用。
