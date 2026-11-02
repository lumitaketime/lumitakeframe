# Lumitake Library：地端 AI 圖片管理

用**本機執行的視覺模型**掃描硬碟／外接 SSD 裡的照片，自動產生描述、關鍵字與圖中文字，
之後只要輸入關鍵字（例如「貓 沙發」「海邊 夕陽」「year:2023 folder:京都」）就能找出照片在哪裡，
一鍵在檔案總管／Finder 中顯示原檔。

- **完全地端**：圖片只送到你電腦上的 [Ollama](https://ollama.com)，不上傳雲端。
- **不搬動、不修改原檔**：圖庫只保存路徑、分析結果與縮圖（在 `~/.lumilib`）。
- **增量掃描**：只處理新增或修改的檔案；分析可隨時中斷，下次從未完成的圖片繼續。
- **找得回搬移的檔案**：檔案改名或換資料夾，重新掃描後用內容指紋找回，原本的分析保留。
- **外接 SSD 友善**：硬碟沒接上時不會把照片當成刪除；換了磁碟代號用 `relocate` 一行修正。
- **重複照片**：內容相同的副本直接沿用分析結果，不重複耗時。
- **搜尋**：中英文關鍵字、片語、排除、日期、相機、資料夾、副檔名條件；可選語意搜尋。
- **手動標籤與備註**：可在網頁介面補充，例如「家人」「作品集」，一樣能搜尋。
- 支援 JPG、PNG、WebP、GIF、BMP、TIFF、HEIC／HEIF（需 `pillow-heif`）、AVIF（視 Pillow 版本）。

## 1. 安裝

需要 Python 3.10 以上。

```sh
cd image-library
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS / Linux: source .venv/bin/activate
pip install -e ".[all]"
```

`[all]` 會一併安裝 HEIC 支援（pillow-heif）與加速語意搜尋的 numpy；只需要基本功能可用 `pip install -e .`。

接著安裝 [Ollama](https://ollama.com/download) 並下載視覺模型：

```sh
ollama pull qwen2.5vl:7b
lumilib doctor          # 檢查連線、模型與選用套件
```

### 模型選擇

| 模型 | 大小 | 說明 |
| --- | --- | --- |
| `qwen2.5vl:7b`（預設） | 約 6 GB | 中文描述與圖中文字辨識表現好，建議 8 GB 以上顯示記憶體 |
| `qwen2.5vl:3b` | 約 3 GB | 較快、較省記憶體，細節略少 |
| `gemma3:4b` / `gemma3:12b` | 3–8 GB | 多語言，另一種選擇 |
| `qwen3-vl:8b` 等較新模型 | — | Ollama 有提供的支援圖片輸入模型都可以使用 |

更換模型：`lumilib config set vision_model qwen2.5vl:3b`。換模型後想全部重新分析可用 `lumilib analyze --redo`。

速度參考：一般顯示卡每張數秒，只用 CPU 每張可能數十秒。上萬張照片建議放著過夜跑，隨時可中斷。

## 2. 使用

```sh
# 加入照片資料夾（可以是整顆外接 SSD），會立即掃描
lumilib add "E:\\" --name 照片SSD
lumilib add ~/Pictures --name 電腦相簿

# 用地端模型分析所有尚未分析的圖片（Ctrl+C 可中斷，下次繼續）
lumilib analyze

# 搜尋
lumilib search 貓 沙發
lumilib search "日落 海邊" year:2023
lumilib search 收據 --paths          # 只輸出完整路徑，方便複製或交給其他程式

# 網頁介面（建議）
lumilib serve --open
```

網頁介面在 `http://127.0.0.1:8765/`，可搜尋、看大圖、點關鍵字找相似主題、編輯手動標籤、
在檔案總管中顯示原檔，也能直接按「掃描並分析」。介面只對本機開放。

### 日常維護

```sh
lumilib index        # 新增照片後：掃描全部資料夾 + 分析新圖片
lumilib stats        # 統計
lumilib roots        # 列出資料夾與是否連接
lumilib relocate 照片SSD "F:\\"   # SSD 換了磁碟代號 / 掛載位置
lumilib analyze --retry-failed     # 重試先前失敗的圖片
lumilib tag 123 --add 家人 旅行 --note "外婆生日"
```

## 3. 搜尋語法

| 範例 | 意思 |
| --- | --- |
| `貓 沙發` | 同時包含兩個關鍵字 |
| `"日落 海邊"` | 完整片語 |
| `-狗` | 排除 |
| `tag:貓` | 只比對關鍵字欄位（模型 + 手動標籤） |
| `folder:京都` | 路徑包含 |
| `camera:iphone` | 相機型號 |
| `ext:heic` | 副檔名 |
| `year:2023`、`after:2023-05-01`、`before:2023-06-01` | 拍攝日期（after 含當天，before 不含） |
| `root:照片SSD` | 指定資料夾 |
| `is:pending` `is:failed` `is:missing` `is:analyzed` | 狀態 |

關鍵字會比對：模型描述、關鍵字（含英文同義詞）、場景、物品、圖中文字、檔名與資料夾名稱、相機、手動標籤與備註。
模型分析時也會參考資料夾名稱（例如「2023 京都旅行」），只在與畫面相符時採用。

### 語意搜尋（選用）

關鍵字搜尋需要字面相符；語意搜尋能讓「沙灘」找到描述寫「海邊」的照片。

```sh
ollama pull bge-m3
lumilib config set embed_model bge-m3
lumilib embed                       # 為已分析的圖片建立向量（之後 analyze 會自動建立）
lumilib search 沙灘 --semantic
```

網頁介面搜尋框旁會出現「語意」勾選框。結果先列出關鍵字相符的，再補上語意相近的（標示「語意相近」／`≈`）。

## 4. 設定

`lumilib config` 查看目前設定，`lumilib config set <key> <value>` 修改，也可用環境變數 `LUMILIB_<KEY>`。

| key | 預設 | 說明 |
| --- | --- | --- |
| `vision_model` | `qwen2.5vl:7b` | 視覺模型 |
| `embed_model` | （空） | 向量模型，設定後啟用語意搜尋 |
| `language` | `zh-TW` | 描述與關鍵字語言：`zh-TW` 或 `en` |
| `ollama_url` | `http://127.0.0.1:11434` | 可指向區網內另一台有 GPU 的電腦 |
| `analyze_max_side` | `1024` | 送進模型前縮小到的長邊像素 |
| `thumb_size` | `360` | 縮圖大小 |
| `request_timeout` | `300` | 每張圖片的模型逾時秒數 |

資料目錄預設 `~/.lumilib`（`library.db` 與 `thumbs/`），可用 `--home` 或 `LUMILIB_HOME` 改到其他位置；
想讓圖庫跟著外接 SSD 走，可以把資料目錄也放在 SSD 上。

## 5. 隱私與安全

- 圖片只送到 `ollama_url`（預設本機）。若改成區網位址，圖片會經由區網傳到那台電腦。
- 網頁服務預設只綁定 `127.0.0.1`，並檢查 Host／Origin，防止其他網站透過瀏覽器存取。
- 不會刪除、移動或修改原始照片；`remove` 只移除圖庫紀錄。
- 模型提示要求不猜測人物身分；本工具不做人臉辨識。

## 6. 開發

```sh
python -m unittest discover -s tests
```

測試使用合成圖片與假模型，不需要 Ollama。

| 檔案 | 內容 |
| --- | --- |
| `lumilib/scanner.py` | 掃描、指紋、搬移／重複偵測 |
| `lumilib/analyzer.py` | Ollama 呼叫、提示詞、結果正規化、向量 |
| `lumilib/search.py` | 查詢語法、排序、語意搜尋 |
| `lumilib/db.py` | SQLite 結構與資料夾管理 |
| `lumilib/server.py`、`lumilib/static/` | 本機網頁介面 |
| `lumilib/cli.py` | 命令列 |
