# Lumi take frame

免費、在裝置內處理的照片畫框工具。支援 HEIC／HEIF、JPG、PNG、WebP，
自動讀取相機與曝光資訊，提供經典白框、純框與可拖曳裁切的拍立得畫框。

- 原尺寸 PNG 無損編碼 / JPG 有損編碼 / 不加框原檔下載
- 手動編輯 EXIF 顯示文字，獨立控制相機與參數顯示
- 方形與直式拍立得，完整保留或填滿裁切
- 行動裝置底部設定與下載、中英文、明暗模式
- 其他版型：照片內文字、資訊橫幅、無框

## 隱私

照片與 EXIF 在瀏覽器內處理，應用程式不將照片上傳，不含廣告、追蹤或帳號系統。
主機供應商仍可能記錄一般網站連線資訊。語言與主題偏好保存在裝置的 localStorage。
PNG/JPG 輸出是重新繪製的圖像，不承諾保留來源 HDR、色彩描述檔或原始 EXIF；
需要完全保留檔案時請使用原檔下載。超大圖片的匯出能力取決於瀏覽器與裝置記憶體。

## 開發

Node.js 24，pnpm 11.19.0。

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm run check
pnpm test
pnpm run build
```

建置結果在 `dist/`。Vite 使用相對資源路徑，可放在 GitHub Pages 的專案子目錄。

## GitHub Pages

1. 將這個目錄發布到自己的 GitHub 儲存庫，使用 `main` 分支。
2. Settings → Pages → Source 選擇 **GitHub Actions**。
3. 推送 main 後，Pages 工作流程會檢查、測試、建置並發布。
4. 網址由該工作流程的 deployment 輸出提供。

發布檔案不包含測試照片。要驗證自己的 HEIC，可在本機介面選入照片，
確認 EXIF 欄位、方向、裁切與下載。自動測試使用合成 HEIF 標頭及數值，不含私人圖片。

## 實作來源與授權

本專案保留此開發過程中自行設計的介面、HEIC 相容性處理與拍立得繪圖，
另外重寫主繪圖器、照片資訊格式化及建置部署流程。
不包含 `ssssota/exif.photos` 的應用程式原始碼、靜態素材或 Git 歷史。

向 [ssssota/exif.photos](https://github.com/ssssota/exif.photos) 的構想致敬；
本專案為獨立社群工具，並非原作者授權的官方接班網站。

自有程式採非商用、須署名的自訂授權，詳見 LICENSE；文字與原創視覺設計採
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)。這是公開原始碼專案，
不是 OSI 定義的開源軟體。網站僅供非商業使用，分享製作成品須註明工具與連結，
詳見 [使用條款](public/terms.html)。使用者照片著作權仍屬使用者。
第三方套件各自適用其授權，詳見
[第三方聲明](public/THIRD-PARTY-NOTICES.txt) 與 `public/licenses/`。
