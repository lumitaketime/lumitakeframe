# Lumitake Library：離線 AI 照片與影片圖庫

> **Re'memor 開發中（`rememor` 分支）**：在這個圖庫的基礎上，加上「硬碟拔掉也能查」的完整硬碟目錄。
> 規劃見 [docs/rememor-plan.md](../docs/rememor-plan.md)。目前已完成：
> - **硬碟目錄**：掃描時記錄每個資料夾、每個檔案（照片、文件、音樂、壓縮檔…所有類型）的名稱、大小、日期與類型，
>   以及每個資料夾含子資料夾的總大小。硬碟拔掉後，在「資料夾」頁照樣可以瀏覽。
> - **認得每一顆硬碟**：用系統的硬碟編號辨識；硬碟改名後自動找到新位置，同一個位置換成另一顆硬碟時不會混在一起掃描。
> - **可中斷、可接續**：掃描中途拔掉硬碟或按停止，不會把還沒掃到的檔案標成遺失，下次從中斷處繼續。
> - **只讀不寫硬碟**：掃描時不修改、不建立硬碟上的任何檔案。

給攝影師用的本機圖庫，概念像 Android 相簿：**資料夾就是相簿來源，App 只負責瀏覽與整理**。
照片和影片留在你的 SSD／硬碟原位，不會被複製進某個資料庫，也不會上傳雲端。
介面參考 Google 相簿與 Immich，Mac 用瀏覽器開，iPhone／iPad 透過家裡 Wi-Fi 也能看。

## 功能

- **時間軸**：依拍攝日期分月、分日，等高列排版，右側時間捲軸快速跳到任何年月。
- **資料夾**：照硬碟上的資料夾結構瀏覽，可在 Finder 中打開。
- **相簿與我的最愛**：同一張照片可放進多個相簿，不會複製檔案。
- **AI 分析（地端）**：Ollama 上的視覺模型產生中文描述、中英文關鍵字、圖中文字；影片取 4 個畫面一起分析。
  模型可在設定頁下載、切換、刪除。
- **搜尋**：中英文關鍵字、片語、排除，以及相機、鏡頭、日期、資料夾、檔案類型等條件；可選語意搜尋。
- **完整檔案資訊**：拍攝時間（含時區）、相機、鏡頭、光圈、快門、ISO、焦距、尺寸、GPS 與地名、
  檔案內的關鍵字與標題、檔案完整路徑（點一下複製、在 Finder 中顯示、前往資料夾）。
- **人臉辨識**：InsightFace 模型在本機偵測人臉並自動分群成「人物」，命名後可直接搜尋名字
  （例如 `新郎 海邊`）；可合併、隱藏、更正「不是這個人」，臉部資料只存在本機。
- **智慧搜尋（跨語言）**：AI 把搜尋詞翻譯並擴充成中英文同義詞（「貓」也找 cat、kitten），
  加上多語言 CLIP 圖像搜尋直接比對畫面內容，即使照片還沒有 AI 描述也找得到。
  英文描述可一鍵翻譯成中文。
- **星等與標籤**：星等（含拒絕）、顏色標籤、關鍵字只存在圖庫裡，不會改動檔案；
  檢視器使用和 Lightroom 一樣的快捷鍵（0–5 星、6–9 顏色、X 拒絕、U 取消）。
- **疊放**：RAW＋JPEG 同名雙檔、連拍（同相機連續 3 張以上）自動疊成一張，可手動調整封面、解除或疊放。
- **重複與相似照片**：找出完全相同的檔案與幾乎一樣的照片（連拍、縮小再存的版本），建議保留最好的一張，其餘移到垃圾桶。
- **智慧相簿與那年今日**：任何搜尋都能存成會自動更新的相簿（例如 `rating:4 camera:x100vi`）；時間軸上方顯示往年的今天。
- **人物分類**：人物除了名字，還能加上「家人、朋友、同事、客戶、模特兒」或自訂分類，可多選；分類可篩選、可直接搜尋（`客戶 海邊`、`group:客戶`）。
- **關鍵字雲**：依出現在幾張照片排列你最常拍的內容（AI、照片檔案內原有的、自己加的關鍵字），可切換年份或排行榜，點一下看照片。
- **地點**：有 GPS 的照片離線換算成最近的城鎮（例如「恆春鎮，台灣」、「京都，日本」），
  可以直接搜尋地名（中英文皆可），探索頁會列出常去的地點。不需要連網。
- **移到垃圾桶**：先問過你才會移到垃圾桶（可還原）。Lightroom `.xmp` 與 iPhone `.aae`
  附屬檔會一起移動；RAW+JPEG 同名時，`.xmp` 會留給 RAW。
- **格式**：JPG、PNG、WebP、HEIC/HEIF、TIFF、GIF、AVIF；RAW（CR2/CR3/NEF/ARW/RAF/ORF/RW2/DNG 等，
  用內嵌預覽）；影片 MP4、MOV、M4V、AVI、MKV、MTS 等（瀏覽器可播放 MP4／MOV，其他格式可在 Mac 上開啟）。
- **找得回來**：檔案在 Finder 改名或搬移後，重新掃描會用內容指紋找回，分析與相簿都保留；
  外接 SSD 沒接上時不會被當成刪除；SSD 換了名稱可在設定頁更新位置。
- **手機與平板**：在設定頁設定密碼、開啟「手機連線」，用 iPhone 相機掃 QR code，
  Safari「加入主畫面」後像 App 一樣全螢幕使用。

## 安裝

所有安裝檔都在 GitHub 的 **Releases → 「Lumitake Library 最新版」**（`app-latest`），每次更新程式後自動重新建置。

### Mac App（建議）

1. 下載 `Lumitake-Library-mac.dmg`（Apple Silicon：M1 以後的 Mac），打開後把 App 拖進「應用程式」。
2. 第一次打開時，macOS 會說無法驗證開發者（這個 App 沒有付費的 Apple 簽章）：
   到「系統設定 → 隱私權與安全性」，往下找到 Lumitake Library，按「仍要打開」。
   如果出現「已損毀，無法打開」，在終端機執行一次：

   ```bash
   xattr -cr "/Applications/Lumitake Library.app"
   ```

3. 第一次打開會出現「設定引導」：加入照片資料夾 → 安裝 [Ollama](https://ollama.com/download)（畫面會一步一步說明並自動偵測）
   → 依你的 Mac 下載推薦的模型。模型下載完後到「設定 → AI 分析」開始分析（預設不會自動分析每張照片，
   要自動分析可以在那裡開啟）。之後可在「設定 → 外觀與系統」重新執行引導。
   exiftool、ffmpeg 已經內建在 App 裡，不用另外安裝。
4. 關閉視窗後 App 會留在上方選單列（手機才能繼續連線）；要完全結束請按選單列圖示 →「結束」。
   選單裡也可以勾選「登入時自動啟動」。

App 與命令列版本共用同一個圖庫資料（`~/.rememor`），分析結果、相簿、人物都會保留。
Re'memor 和 Lumitake Library 分開存放（Library 在 `~/.lumilib`、連接埠 8765；Re'memor 在 `~/.rememor`、連接埠 8766），
兩個可以同時使用，不會讀寫到對方的資料。
如果之前用終端機安裝過（桌面上有 `Lumitake Library.command`），App 開啟時會自動關閉舊版服務、改用 App 內建的新版；
之後請直接用 App，可以把桌面上的 `Lumitake Library.command` 刪掉。

### Android App

1. 在手機下載 `Lumitake-Library.apk` 並安裝（需允許「安裝不明來源的應用程式」）。
2. Mac 上打開「設定 → 手機與平板」，設定密碼並開啟連線。
3. 打開手機 App，掃描 Mac 畫面上的 QR code，輸入密碼。
4. 照片頁的「存到這台裝置」會存到手機的「圖片/Lumitake」。長按 App 圖示可以「更換連線」。

介面來自 Mac，Mac 更新後手機自動是新版，APK 很少需要更新。
更新 APK 時如果無法直接覆蓋安裝，先解除安裝舊版即可（只要重新掃一次 QR code）。

### iPhone／iPad

用 Safari 開啟 Mac 設定頁顯示的網址，登入後按「分享 →『加入主畫面』」，就能像 App 一樣全螢幕使用。

### 進階：用終端機安裝（開發用）

```bash
bash ~/Downloads/lumitakeframe-claude-kind-dijkstra-7t80hs/image-library/install-mac.sh
```

會用 Homebrew 安裝 Python、exiftool、ffmpeg、Ollama，並在桌面建立 `Lumitake Library.command`。

### 推薦模型

App 會偵測 Mac 的記憶體，在「設定 → AI 分析」標出「品質優先」與「速度優先」的模型。
下表是在 4 核心 CPU 測試機上用真的 Ollama 實測的結果（Apple Silicon 用 GPU 會快很多）：

| 模型 | 下載大小 | 測試機每張 | 結果 |
| --- | --- | --- | --- |
| `gemma4:e4b` | 6.6 GB | 約 90 秒 | 16GB Mac 預設。描述自然、關鍵字中英對照、圖中文字正確 |
| `gemma4:e2b` | 4.6 GB | 約 40 秒 | 速度優先、8GB Mac。品質略簡單但正確 |
| `gemma4:26b` / `gemma4:31b` | 18–20 GB | 未實測 | 32GB／48GB 以上的 Mac |
| `qwen3-vl:4b` | 3.3 GB | 超過 10 分鐘 | 實測很慢，暫不建議 |
| `bge-m3` | 1.2 GB | 很快 | 語意搜尋（選用） |

分析可以隨時停止，下次會接著做。也可以到資料夾或相簿頁只分析特定作品。

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
  選取後上方會出現：加入最愛、加到相簿、AI 分析、移到垃圾桶。
- 檢視器快捷鍵：← → 切換、`i` 資訊、`f` 最愛、Delete 刪除、Esc 關閉、滾輪／雙擊縮放。
- 搜尋語法：

  | 範例 | 意思 |
  | --- | --- |
  | `貓 沙發` | 同時包含（描述、關鍵字、圖中文字、檔名、資料夾） |
  | `"日落 海邊"` | 完整片語 |
  | `-狗` | 排除 |
  | `tag:作品集` | 只找關鍵字（AI、檔案內原有的、手動標籤） |
  | `folder:婚禮` `camera:x-t5` `lens:56mm` | 資料夾、相機、鏡頭 |
  | `year:2024` `after:2024-05-01` `before:2024-06-01` | 日期 |
  | `type:video` `type:raw` `ext:heic` | 類型 |
  | `person:媽媽` | 人物（人臉辨識後命名） |
  | `rating:4` `label:紅` `is:rejected` | 星等（以上）、顏色標籤、被拒絕 |
  | `group:客戶` | 人物分類 |
  | `place:恆春`，或直接輸入 `京都` | 地點（依 GPS 換算） |
  | `is:favorite` `is:pending` `is:failed` `is:missing` | 狀態 |

### 把圖庫資料也放在 SSD（行動作品集）

資料庫與縮圖預設在 `~/.rememor`（十萬張約 2–3 GB 縮圖）。想讓它跟著 SSD 走，
先結束 App，在終端機把資料搬到 SSD 並建立捷徑（`你的SSD` 換成實際名稱）：

```bash
mv ~/.rememor "/Volumes/你的SSD/.rememor" && ln -s "/Volumes/你的SSD/.rememor" ~/.rememor
```

之後 App 會透過這個捷徑讀寫 SSD 上的資料；使用時 SSD 需要接著。

### 手機與平板

1. 設定 → 手機與平板：設定密碼、勾選「允許手機與平板連線」、按「立即重新啟動」。
   macOS 詢問是否允許 Python 接受連入連線時選「允許」。
2. iPhone 連同一個 Wi-Fi，用相機掃設定頁的 QR code，輸入密碼。
3. Safari 分享選單 →「加入主畫面」。

Mac 需要保持開機（接電源時程式會避免睡眠，但闔上螢幕仍會睡眠），SSD 需要接著。
從手機按「在 Finder 中顯示」會在 Mac 上打開 Finder。出門在外的連線（例如 Tailscale）之後再加。

## 隱私與安全

- 照片只送到這台 Mac 上的 Ollama（`http://127.0.0.1:11434`），不上傳任何雲端服務。
- 地名換算使用內附的離線資料，不會連網。
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
python tools/bench_catalog.py 100000   # 用十萬個假檔案量目錄掃描的速度

# 前端（Svelte 5 + Vite），建置結果輸出到 lumilib/web/ 並一起提交，安裝時不需要 Node.js
cd web && pnpm install && pnpm build
pnpm dev   # 開發模式，API 轉到 127.0.0.1:8766
```

| 位置 | 內容 |
| --- | --- |
| `lumilib/media.py` | exiftool／Pillow／ffmpeg：EXIF、RAW 預覽、影片畫面、縮圖 |
| `lumilib/scanner.py` | 硬碟目錄與照片的增量掃描：拔掉硬碟的處理、接續掃描、同一顆硬碟內的搬移偵測 |
| `lumilib/volumes.py` | 用系統的硬碟編號辨識每一顆硬碟（不在硬碟上寫入任何東西） |
| `lumilib/filetypes.py` | 依副檔名分類：照片、RAW、影片、音樂、文件、壓縮檔、套件 |
| `lumilib/catalog.py` | 目錄查詢：資料夾總大小、資料夾內容（硬碟拔掉也能查） |
| `lumilib/analyzer.py`、`models.py` | Ollama 呼叫、提示詞、模型下載與推薦清單 |
| `lumilib/search.py` | 查詢語法、排序、語意搜尋 |
| `lumilib/fileops.py` | 垃圾桶、附屬檔、Finder |
| `lumilib/faces.py` | 人臉偵測（SCRFD）、對齊、特徵（ArcFace）、分群、人物操作 |
| `lumilib/clip.py` | 多語言 CLIP 圖像搜尋：模型下載、索引、排序 |
| `lumilib/places.py` | 離線地名（GeoNames 資料，CC BY 4.0） |
| `lumilib/ratings.py` | 星等、顏色標籤、關鍵字（只存在圖庫） |
| `lumilib/organize.py` | 疊放、重複與相似照片、智慧相簿、那年今日 |
| `lumilib/keywords.py` | 關鍵字雲 |
| `lumilib/server.py`、`auth.py`、`jobs.py` | FastAPI、登入、背景工作佇列 |
| `web/src/` | PWA 介面：時間軸、檢視器、資料夾、相簿、設定 |
| `desktop/` | Mac App（Tauri 外殼、PyInstaller 打包的伺服器、啟動畫面） |
| `android/` | Android App（WebView 外殼、QR 配對、下載） |
| `../.github/workflows/apps.yml` | 自動建置 DMG 與 APK 並發布到 Releases |

## 接下來

- 出門在外連線（Tailscale）
- Windows 版
