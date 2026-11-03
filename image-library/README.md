# Lumitake Library：離線 AI 照片與影片圖庫

給攝影師用的本機圖庫，概念像 Android 相簿：**資料夾就是相簿來源，App 只負責瀏覽與整理**。
照片和影片留在你的 SSD／硬碟原位，不會被複製進某個資料庫，也不會上傳雲端。
介面參考 Google 相簿與 Immich，Mac 用瀏覽器開，iPhone／iPad 透過家裡 Wi-Fi 也能看。

## 功能

- **時間軸**：依拍攝日期分月、分日，等高列排版，右側時間捲軸快速跳到任何年月。
- **資料夾**：照硬碟上的資料夾結構瀏覽，可建立資料夾、在 Finder 中打開。
- **相簿與我的最愛**：同一張照片可放進多個相簿，不會複製檔案。
- **AI 分析（地端）**：Ollama 上的視覺模型產生中文描述、中英文關鍵字、圖中文字；影片取 4 個畫面一起分析。
  模型可在設定頁下載、切換、刪除。
- **搜尋**：中英文關鍵字、片語、排除，以及相機、鏡頭、日期、資料夾、檔案類型等條件；可選語意搜尋。
- **完整檔案資訊**：拍攝時間（含時區）、相機、鏡頭、光圈、快門、ISO、焦距、尺寸、GPS 與地圖、
  Lightroom 關鍵字與標題、檔案完整路徑（點一下複製、在 Finder 中顯示、前往資料夾）。
- **人臉辨識**：InsightFace 模型在本機偵測人臉並自動分群成「人物」，命名後可直接搜尋名字
  （例如 `新郎 海邊`）；可合併、隱藏、更正「不是這個人」，臉部資料只存在本機。
- **智慧搜尋（跨語言）**：AI 把搜尋詞翻譯並擴充成中英文同義詞（「貓」也找 cat、kitten），
  加上多語言 CLIP 圖像搜尋直接比對畫面內容，即使照片還沒有 AI 描述也找得到。
  英文描述可一鍵翻譯成中文。
- **地圖與地點**：有 GPS 的照片顯示在 OpenStreetMap 上；並離線換算成最近的城鎮（例如「恆春鎮，台灣」、
  「京都，日本」），可以直接搜尋地名（中英文皆可），探索頁會列出常去的地點。
- **真的整理硬碟**：搬移到其他資料夾、移到垃圾桶（可還原）。Lightroom `.xmp` 與 iPhone `.aae`
  附屬檔會跟著走；RAW+JPEG 同名時，`.xmp` 會留給 RAW。
- **格式**：JPG、PNG、WebP、HEIC/HEIF、TIFF、GIF、AVIF；RAW（CR2/CR3/NEF/ARW/RAF/ORF/RW2/DNG 等，
  用內嵌預覽）；影片 MP4、MOV、M4V、AVI、MKV、MTS 等（瀏覽器可播放 MP4／MOV，其他格式可在 Mac 上開啟）。
- **找得回來**：檔案在 Finder 改名或搬移後，重新掃描會用內容指紋找回，分析與相簿都保留；
  外接 SSD 沒接上時不會被當成刪除；SSD 換了名稱可在設定頁更新位置。
- **手機與平板**：在設定頁設定密碼、開啟「手機連線」，用 iPhone 相機掃 QR code，
  Safari「加入主畫面」後像 App 一樣全螢幕使用。

## 安裝（macOS）

1. 下載這個專案（GitHub 頁面 → Code → Download ZIP，解壓縮）。
2. 打開「終端機」，把 `install-mac.sh` 拖進視窗前面加上 `bash `，按 Enter：

   ```bash
   bash ~/Downloads/lumitakeframe-main/image-library/install-mac.sh
   ```

   會自動安裝 Homebrew、Python、exiftool、ffmpeg、Ollama，並詢問是否下載推薦的 AI 模型（約 6 GB）。
   過程中可能需要輸入 Mac 的登入密碼。
3. 完成後桌面會出現 **Lumitake Library.command**，點兩下就會啟動並開啟瀏覽器。
   關閉那個終端機視窗即停止。
4. 第一次使用：到「設定 → 圖庫資料夾」按「選擇資料夾…」，練習可先加入 `~/Pictures`。

### 推薦模型（M1 Pro 16GB）

| 模型 | 大小 | 速度 | 用途 |
| --- | --- | --- | --- |
| `qwen2.5vl:7b` | 約 6 GB | 每張 6–12 秒 | 預設，中文描述與文字辨識最好 |
| `qwen2.5vl:3b` | 約 3 GB | 每張 3–5 秒 | 十萬張先快速掃一輪 |
| `qwen3-vl:8b` / `qwen3-vl:4b` | 3–6 GB | 中／快 | 新一代，需要較新版 Ollama |
| `gemma3:12b` | 約 8 GB | 每張 12–25 秒 | 描述細膩，16GB 會比較吃緊 |
| `bge-m3` | 約 1.2 GB | 很快 | 語意搜尋（選用） |

十萬張照片用 7B 模型大約需要一到兩週的累積時間。建議：先用 3B 掃一輪，
重要作品再到資料夾或相簿頁按「AI 分析」用 7B 重跑。分析可以隨時停止，下次會接著做。

### 人臉辨識與圖像搜尋

到「設定」：
- **人臉辨識**：下載 `buffalo_l`（約 289 MB，推薦）或 `buffalo_s`（輕量），按「偵測人臉」。
  M1 上每張約 0.05–0.1 秒，十萬張約 2–3 小時。同一個人出現 3 次以上會成為一個人物，到「人物」頁命名。
  勾選「掃描新照片時自動偵測人臉」後，之後新增的照片會自動處理。
- **智慧搜尋**：預設開啟（使用目前的視覺模型翻譯搜尋詞）。
- **圖像搜尋**：下載多語言 CLIP 模型（從 Hugging Face），勾選啟用後會建立索引（十萬張約半小時）。

InsightFace 預訓練模型的授權僅限非商業用途。

## 日常使用

- 新照片放進 SSD 資料夾後，重新開啟程式（預設啟動時自動掃描），或到設定按「重新掃描」。
- 選取：滑鼠移到照片左上角點圓圈，按住 Shift 可選一整段；手機上長按。
  選取後上方會出現：加入最愛、加到相簿、搬移、AI 分析、移到垃圾桶。
- 檢視器快捷鍵：← → 切換、`i` 資訊、`f` 最愛、Delete 刪除、Esc 關閉、滾輪／雙擊縮放。
- 搜尋語法：

  | 範例 | 意思 |
  | --- | --- |
  | `貓 沙發` | 同時包含（描述、關鍵字、圖中文字、檔名、資料夾） |
  | `"日落 海邊"` | 完整片語 |
  | `-狗` | 排除 |
  | `tag:作品集` | 只找關鍵字（AI、Lightroom、手動標籤） |
  | `folder:婚禮` `camera:x-t5` `lens:56mm` | 資料夾、相機、鏡頭 |
  | `year:2024` `after:2024-05-01` `before:2024-06-01` | 日期 |
  | `type:video` `type:raw` `ext:heic` | 類型 |
  | `person:媽媽` | 人物（人臉辨識後命名） |
  | `place:恆春`，或直接輸入 `京都` | 地點（依 GPS 換算） |
  | `is:favorite` `is:pending` `is:failed` `is:missing` | 狀態 |

### 把圖庫資料也放在 SSD（行動作品集）

資料庫與縮圖預設在 `~/.lumilib`（十萬張約 2–3 GB 縮圖）。想讓它跟著 SSD 走：
用文字編輯器打開桌面的 `Lumitake Library.command`，把這行的註解拿掉並改成你的 SSD：

```bash
export LUMILIB_HOME="/Volumes/你的SSD/.lumilib"
```

### 手機與平板

1. 設定 → 手機與平板：設定密碼、勾選「允許手機與平板連線」、按「立即重新啟動」。
   macOS 詢問是否允許 Python 接受連入連線時選「允許」。
2. iPhone 連同一個 Wi-Fi，用相機掃設定頁的 QR code，輸入密碼。
3. Safari 分享選單 →「加入主畫面」。

Mac 需要保持開機（接電源時程式會避免睡眠，但闔上螢幕仍會睡眠），SSD 需要接著。
從手機按「在 Finder 中顯示」會在 Mac 上打開 Finder。出門在外的連線（例如 Tailscale）之後再加。

## 隱私與安全

- 照片只送到這台 Mac 上的 Ollama（`http://127.0.0.1:11434`），不上傳任何雲端服務。
- 地圖圖磚來自 OpenStreetMap，只會傳送地圖位置，不會傳送照片。
- 預設只允許本機連線；開啟手機連線後，其他裝置一律需要密碼（scrypt 雜湊保存）。
  選資料夾、改連線設定只能在 Mac 本機操作。服務會檢查 Host／Origin，防止其他網站透過瀏覽器呼叫。
- 刪除一律移到垃圾桶；「從圖庫移除資料夾」只刪紀錄，不動硬碟上的檔案。

## 命令列（進階）

```bash
cd image-library && source .venv/bin/activate
lumilib doctor                    # 檢查 Ollama、模型、exiftool、ffmpeg
lumilib add "/Volumes/SSD/作品" --name 作品集SSD
lumilib analyze --limit 100       # 分析 100 張
lumilib search 海邊 夕陽 --paths   # 只輸出完整路徑
lumilib relocate 作品集SSD "/Volumes/新名稱/作品"
lumilib password                  # 設定手機連線密碼
lumilib serve --open
```

## 開發

```bash
# 後端測試（不需要 Ollama；有 exiftool / ffmpeg 時會多跑相關測試）
pip install -e ".[test]" && python -m unittest discover -s tests

# 前端（Svelte 5 + Vite），建置結果輸出到 lumilib/web/ 並一起提交，安裝時不需要 Node.js
cd web && pnpm install && pnpm build
pnpm dev   # 開發模式，API 轉到 127.0.0.1:8765
```

| 位置 | 內容 |
| --- | --- |
| `lumilib/media.py` | exiftool／Pillow／ffmpeg：EXIF、RAW 預覽、影片畫面、縮圖 |
| `lumilib/scanner.py` | 增量掃描、內容指紋、搬移與重複偵測 |
| `lumilib/analyzer.py`、`models.py` | Ollama 呼叫、提示詞、模型下載與推薦清單 |
| `lumilib/search.py` | 查詢語法、排序、語意搜尋 |
| `lumilib/fileops.py` | 垃圾桶、搬移、附屬檔、Finder |
| `lumilib/faces.py` | 人臉偵測（SCRFD）、對齊、特徵（ArcFace）、分群、人物操作 |
| `lumilib/clip.py` | 多語言 CLIP 圖像搜尋：模型下載、索引、排序 |
| `lumilib/places.py` | 離線地名（GeoNames 資料，CC BY 4.0） |
| `lumilib/server.py`、`auth.py`、`jobs.py` | FastAPI、登入、背景工作佇列 |
| `web/src/` | PWA 介面：時間軸、檢視器、資料夾、相簿、地圖、設定 |

## 接下來

- 出門在外連線（Tailscale）、Windows 版
