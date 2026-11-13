依 Apple《Human Interface Guidelines》整理的交互設計系統，以 Liquid Glass 設計語言為核心，**macOS 優先、兼顧 iOS／iPadOS**。這是非官方的整理與網頁實作，不是 Apple 產品；原生 App 一律以系統元件、系統色與 SF 字體為準，本系統的值是設計與原型時的參考。

## 三個原則

Liquid Glass 的設計建立在三件事上：

- **層次（Hierarchy）**：控制項與導覽浮在內容之上的玻璃功能層，內容在下方的內容層。兩層各司其職，內容永遠是主角。
- **和諧（Harmony）**：形狀與硬體、手指的圓弧呼應——膠囊、圓形、同心圓角；介面元件的圓角與它的容器同心。
- **一致（Consistency）**：同一套樣式在 Mac、iPhone、iPad 上自動適應；同一個意思只用同一種顏色、同一個符號、同一個詞。

## 內容原則（Writing）

- **先決定語氣，再依情境調整**：本系統的語氣是清楚、直接、不賣弄。能用更少的字就用更少的字；不確定時唸出來聽聽看。
- **按鈕與連結用動詞**：「傳送」比「來吧！」好；不要寫「按這裡」。流程開頭用「開始使用」，中間一致用「繼續」或「下一步」，結尾用「完成」。
- **少用所有格，不用「我們」**：寫「個人收藏」而不是「你的個人收藏」；寫「無法載入內容」而不是「我們在載入內容時遇到問題」。
- **錯誤訊息**：放在問題旁邊、不責怪、說清楚怎麼修正。✓「請使用至少 8 個字元的密碼。」✗「無效的密碼」「哎呀！」。用正向描述：✓「名稱只能使用文字」✗「不要使用數字或符號」。
- **空狀態**：說明下一步，並盡量附一個按鈕或連結。
- **設定**：標籤清楚，說明開啟時會發生什麼；需要時直接連到該設定，不要描述它在哪裡。
- **裝置用語**：觸控裝置說「點一下」，Mac 說「按一下」。
- **英文大小寫**：選單項目、按鈕、Alert 的片語標題用標題式大小寫（Title Case），完整句子用句子式；同一類元素一律同一種。
- **繁體中文排版**：中文與英文、數字之間加半形空格（「iCloud 照片」「共 1,284 張」）；中文用全形標點；刪節號用「…」（單一字元）。
- **Alert 文字**：標題具體（✗「錯誤」），按鈕一到兩個詞描述結果（刪除、退出、再試一次），取消一律叫「取消」，「好」只用於純資訊。
- **Emoji**：介面文字不使用 emoji；符號一律用 SF Symbols（網頁原型用本系統的 `Icon`）。

## 視覺基礎

### 色彩

- **用語意色，不要寫死色值**。HIG 列出的系統色值只供設計參考，會隨系統版本調整；程式中用 `Color.blue`、`.label`、`NSColor.windowBackgroundColor` 等 API。本系統的 token 名稱一一對應這些 API（見各 token 說明）。
- **四個主題**：淺色、深色、淺色・增強對比、深色・增強對比。HIG 要求所有顏色在淺色、深色、增強對比三種情境都能用；即使 App 只提供一種外觀，也要準備淺色與深色值以支援 Liquid Glass 的自適應。
- **系統色**（`system-red` … `system-brown`、`gray-1` … `gray-6`）的四組值直接取自 HIG 的系統色表。
- **文字**：主要文字 `label-primary`；次要 `label-secondary`；不可用的項目 `label-tertiary`；浮水印 `label-quaternary`；玻璃上的次要文字 `label-glass-secondary`。不要改變語意——不要把 `separator` 當文字色、不要把 `label-secondary` 當背景。
- **背景**：一般畫面 `bg-primary` → `bg-secondary` → `bg-tertiary`；群組列表 `grouped-primary` → `grouped-secondary` → `grouped-tertiary`；深色模式中 Sheet、Popover 用較亮的 `elevated-*`（HIG：base 色較暗使背景退後，elevated 較亮使前景浮起）；macOS 視窗 `window-bg`、表格與欄位內部 `control-bg`。
- **強調色**：`accent`（預設 `system-blue`）用於主要按鈕、選取、連結。破壞性動作用 `destructive`（`system-red`），開關用 `toggle-on`（`system-green`）。
- **不要只靠顏色傳達資訊**：狀態一定附帶文字、符號或位置變化。紅綠、藍橙組合對色盲者難以分辨。也要考慮文化差異——例如股價上漲在英文介面是綠色、在中文介面是紅色。
- **同一個顏色只代表一件事**；顏色用在玻璃上要克制：只替主要動作的**背景**上色，不要讓多個控制項同時上色，也不要替玻璃上的文字或符號上色。

**對比**（HIG Accessibility，以 WCAG AA 為基準）：

| 文字大小 | 字重 | 最低對比 |
|---|---|---|
| 17pt 以下 | 全部 | 4.5:1 |
| 18pt 以上 | 全部 | 3:1 |
| 全部 | 粗體 | 3:1 |

自訂前景／背景配色在深色模式中盡量達到 7:1，尤其是小字。Apple 的部分標準配對未達 4.5:1——白底的 `label-secondary`（3.4:1）、系統藍文字與白字藍底（3.5:1）、白底的 `toggle-on`（2.2:1）；本系統保留原值並在 token 說明中標示。HIG 的做法是：預設未達最低對比時，**至少在「增加對比」開啟時提供高對比配色**——即本系統的兩個增強對比主題，所有文字 ≥ 4.5:1，主要與次要文字 ≥ 7:1，控制項以 ≥ 3:1 的實線（`control-stroke`、`hc-stroke`、`glass-edge`）區隔。

### 字體

- 系統字體是 **SF Pro**（macOS、iOS、iPadOS），繁體中文由系統自動以 **蘋方（PingFang TC）** 搭配。字族 token：`sans`（系統字）、`rounded`（SF Pro Rounded）、`serif`（New York，只在 iOS／iPadOS 與 Mac Catalyst）、`mono`（SF Mono）。不要把系統字體嵌入 App；SF 字體依授權只能用於 Apple 平台的介面與設計稿，網頁上以 `-apple-system` 呼叫裝置內建字體。
- 系統字體以「動態光學尺寸」自動在 Text 與 Display 間過渡並調整字距；設計稿中若工具不支援可變字體，才需要手動挑選光學尺寸與字距。
- **macOS**：預設 13pt、最小 10pt；用 `mac-*` 樣式（Large Title 26 → Caption 10）。macOS 不支援 Dynamic Type。
- **iOS／iPadOS**：預設 17pt、最小 11pt；用 `ios-*` 樣式（Dynamic Type「大」：Large Title 34 → Caption 2 11）。必須支援 Dynamic Type，文字至少能放大到 200%。
- 字重用 Regular、Medium、Semibold、Bold；**避免 Ultralight、Thin、Light**。強調用各樣式的強調字重（`*-em` 樣式）。
- 三行以上的文字避免緊縮行距；不要用陰影增加文字對比。
- 其他平台參考：tvOS 預設 29／最小 23、visionOS 17／12、watchOS 16／12（pt）。

### 版面與尺寸

- **以尺寸類別（compact／regular）決定版面**，不要以裝置型號或方向判斷。
- **安全區與版面邊距**：內容避開硬體與系統列。邊距 iPhone `space-4`（16pt）、iPad 與 macOS 視窗 `space-5`（20pt）——此為 UIKit／AppKit 預設值，HIG 未列數值。
- **命中範圍**（HIG）：iOS／iPadOS 預設 44×44pt、最小 28×28（`target-ios`、`target-ios-min`）；macOS 預設 28×28、最小 20×20（`target-mac`、`target-mac-min`）；visionOS 60×60；tvOS 66×66；watchOS 44×44。
- **間距**（HIG）：有外框（bezel）的元素周圍約 12pt（`space-3`）；沒有外框的元素周圍約 24pt（`space-6`）。其他間距用 4pt 基準的 `space-*`。
- **內容延伸到玻璃之下**：滿版背景延伸到側邊欄、工具列、Tab bar 下方；控制項不墊實心色塊，改用捲動邊緣效果。
- **macOS**：不要把控制項或關鍵資訊放在視窗底部；不要把內容放在相機外殼後方。
- **visionOS**：按鈕中心至少相距 60pt。

### 材質：Liquid Glass 與標準材質

- **兩層**：功能層（工具列、Tab bar、側邊欄、選單、Popover、Alert、按鈕）用 Liquid Glass；內容層用不透明底色或標準材質。**不要在內容層用玻璃**；不要讓玻璃大面積堆疊。
- **regular**（`glass-regular`）為預設，模糊並調整亮度確保可讀；文字多的元件一定用它。**clear**（`glass-clear`）只放在照片、影片之上，底下明亮時加 35% 調暗層（`glass-dim`）。
- 滑桿、開關這類短暫控制項在操作時才呈現玻璃（本系統的圓鈕按住時轉為玻璃）。
- **標準材質**（內容層）：ultraThin、thin、regular、thick——依語意選，不依顏色選；較厚的材質對比較好，較薄的保留更多脈絡。網頁以 `blur-material-*` 近似。
- 材質上的文字與符號用具有 vibrancy 的系統色；`label-quaternary` 不要放在 thin、ultraThin 上。
- 網頁近似：填色 + `backdrop-filter` 模糊 + `shadow-rim` 邊緣高光 + `glass-edge` 細邊；「減少透明度」開啟時改為不透明 `elevated-primary`。

### 形狀與圓角

- 偏好**膠囊**（`radius-capsule`）與**圓形**；獨立按鈕、Tab bar、搜尋欄、工具列群組都是膠囊。
- **同心圓角**：內層圓角 = 外層圓角 − 兩者之間的間距。例如 `radius-xl`（26）的 Alert 內距 `space-4`（16）時，內層按鈕圓角約 10（`radius-md`）或直接用膠囊。
- 標準元件的圓角會與所在的列／容器相配；自訂元件也要做到。
- 圓角數值（`radius-xs` 4 → `radius-2xl` 38）為本系統取值，HIG 未列。

### 陰影與分層

玻璃靠模糊、邊緣高光與輕微陰影浮起：浮在內容上的玻璃用 `shadow-glass`，暫時性層（選單、Popover、Alert、Sheet）用 `shadow-popover`，開關圓鈕用 `shadow-knob`。深色模式陰影更深更集中。內容層不加陰影。

### 動態

- 回饋動態要真實、跟隨手勢，**簡短精確**；頻繁的互動盡量不加動畫。
- 可以中斷：不要讓人等動畫結束才能操作。
- 動態是可選的：同時提供視覺以外的回饋（觸覺、聲音），不要只靠動態傳達資訊。
- Liquid Glass 對直接觸控的回應較強，對觸控式軌跡板較收斂（本系統按住玻璃時放大約 4–6%）。
- **減少動態效果**開啟時：減少自動與重複的動畫（縮放、放大、周邊移動）；彈簧收緊；以淡入淡出取代 x／y／z 位移；避免模糊進出的動畫。本系統在 `prefers-reduced-motion` 下取消位移與縮放。
- 原生實作建議用 SwiftUI 的彈簧預設（`.smooth`、`.snappy`、`.bouncy`），不要自訂時長曲線。

### 狀態

| 狀態 | 表現 |
|---|---|
| 按壓 | 一般按鈕稍微變暗；玻璃按鈕放大並增亮；無框按鈕降至 `opacity-pressed` |
| 停用 | 整體 `opacity-disabled`；文字用 `label-tertiary`；仍保持原位，不隱藏 |
| 選取 | iOS 列表短暫反白後顯示勾號；macOS 列表與選單以 `selection`（強調色）＋ `on-accent` 文字 |
| 鍵盤焦點 | `focus-ring`：3px 實色焦點環（`focus`），在所有表面 ≥ 3:1，以 `:focus-visible` 顯示 |
| 載入 | 按鈕內顯示 spinner，可改標籤（「結帳中…」） |

### 深色模式

- 深色不是淺色的反轉：背景更暗、前景更亮；系統色在深色模式各有一組更亮的值。
- 不要提供 App 專屬的外觀設定，跟隨系統（含「自動」）。
- 內容圖片中的大面積白色在深色模式下要降亮，避免發光。
- 同時測試「增加對比」與「減少透明度」——單獨與一起開啟。

### 無障礙

- 每個控制項都有可被 VoiceOver 讀出的名稱：純圖示按鈕必給 `aria-label`（原生為 accessibilityLabel）；`Icon` 有意義時給 `title`。
- 支援 Dynamic Type 至少 200%（watchOS 140%）；版面要能隨字級重排。
- 提供手勢的替代操作；需要時讓人確認兩次才執行難以復原的動作。
- 不要用會自動消失的計時視圖；讓人控制自動播放。
- 尊重「減少動態效果」「減少透明度」「增加對比」「粗體文字」「降低閃爍光線」。

## 圖示

- **原生 App 一律用 SF Symbols**：與系統字體對齊、提供九種字重與 small／medium（預設）／large 三種比例，以及單色、階層、調色盤、多色四種渲染模式。用「可變色彩」表示隨時間變化的量，不要用來表示深度（深度用階層模式）。
- 符號字重與相鄰文字相配；同一組圖示保持一致的尺寸、細節、筆畫與透視。
- SF Symbols 依授權不可用於 App 圖示、商標或標誌；描繪 Apple 產品的符號不可修改；不要畫 Apple 硬體的仿製圖。
- **網頁與原型**用本系統的 `Icon`（`assets/Icons` 中同名 SVG）：24×24 格線、圓角端點，筆畫依字重 1.7–2.4。它們是 SF Symbols 的網頁替身，不是複製品；交付原生 App 時換回對應的 SF Symbol。
- **App 圖示**（HIG App icons）：iOS／iPadOS／macOS 為 1024×1024 px 方形分層圖（系統套圓角遮罩），提供預設、深色、透明（淺／深）、染色（淺／深）外觀；以 Icon Composer 製作分層並交給系統套用 Liquid Glass 高光與陰影，不要自行烘焙效果；用插畫而非照片，避免過細的線條與文字。watchOS 1088×1088、visionOS 1024×1024（圓形遮罩）、tvOS 800×480（2–5 層視差）。

## 平台對照

| | macOS | iOS／iPadOS |
|---|---|---|
| 預設／最小字級 | 13／10pt（`mac-body`） | 17／11pt（`ios-body`） |
| 命中範圍 | 28×28（最小 20） | 44×44（最小 28） |
| 主要導覽 | 浮動玻璃 `Sidebar` + `Toolbar` | `TabBar`（iPhone 底部、iPad 頂端）＋ `Toolbar` |
| 開關 | `Toggle`、`Checkbox`、`RadioGroup` | `Toggle` 只放在列表列中 |
| 選取回饋 | 強調色反白（`selection`） | 短暫反白＋勾號 |
| 模態 | 附著式 `Sheet`、`Alert` | `Sheet`（medium／large）、`Alert`、`ActionSheet` |
| 版面邊距 | 20pt | 16pt（iPhone）／20pt（iPad） |

## 使用元件

元件在 `components/bundle.js`，全域名稱為 `window.LiquidGlass`，需要頁面先載入 React 18 與 `tokens.css`、`components/bundle.css`。

- 以 `ContentLayer` 包住畫面並指定 `platform`（`mac` 或 `ios`）與 `tone`；裡面的元件會自動套用該平台的尺寸與字級。
- 元件取用的所有顏色、圓角、陰影、尺寸都來自 token；要換強調色，改 `accent` 的別名即可。
- 範例：`h(L.ContentLayer, { platform: 'ios', tone: 'grouped' }, h(L.List, { header: '資料庫' }, h(L.ListRow, { title: '所有照片', icon: 'photo', accessory: 'disclosure', onClick: open })))`。
- `WindowFrame` 只用於版面示意；`ContentLayer tone="media"` 的色塊只是內容替身。
