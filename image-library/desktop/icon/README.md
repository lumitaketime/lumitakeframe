# App 圖示：五個圖層（macOS 26 的六種外觀）

`layers/` 是 Icon Composer 用的五個圖層，由 `make_layers.py` 依設計稿「Re'memor 標誌與圖示」（Mark 母版，預設外觀）產生：

| 檔案 | 內容 |
| --- | --- |
| `1-背景.svg` | 海藍到藏青的漸層，整張正方形（圓角遮罩由系統加上） |
| `2-底層盤.svg` | 最淡的玻璃盤 |
| `3-中層盤.svg` | 中間的玻璃盤 |
| `4-頂層盤.svg` | 最亮的玻璃盤 |
| `5-橘點與波紋.svg` | 唯一的彩色：被找到的檔案 |

高光、陰影、透明與染色由系統的 Liquid Glass 套用，不要烘焙進圖層。

## 什麼時候做

淺色、深色、透明（淺／深）、染色（淺／深）六種外觀只有 macOS 26 以上看得到。
現在的 Mac 是 Sequoia（macOS 15），App 仍然使用 `src-tauri/icons/icon.icns`（一般圖示）。
換到 macOS 26 的電腦後再做下面的步驟並驗收。

## 步驟（在 macOS 26、裝有 Xcode 26 的 Mac 上）

1. 打開 Icon Composer，新增圖示，依序把五個 SVG 拖進去（背景在最下面，橘點在最上面），每個盤子各自一個群組。
2. 盤子群組開啟「Liquid Glass」，橘點群組關閉玻璃效果（保持純色）。
3. 在右上角切換六種外觀檢查：深色外觀可把背景改成近黑的漸層（設計稿的 dark：`#222936` → `#07090d`）。
4. 存成 `Rememor.icon`，放在這個資料夾。
5. 建置時用 `actool` 把 `Rememor.icon` 編進 App（產生 `Assets.car`），並在 Info.plist 加上 `CFBundleIconName = Rememor`；
   `icon.icns` 留著給 macOS 15 以前的系統使用。
