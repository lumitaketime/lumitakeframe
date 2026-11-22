"""SQLite 圖庫與硬碟目錄：硬碟、資料夾根目錄、所有檔案、照片／影片紀錄、分析結果、相簿。

路徑以「根目錄 + 相對路徑」保存。外接 SSD 換了掛載點時用 relocate 更新根目錄即可；
有硬碟編號時，掃描會自動找到改名後的新位置。

v15 新增的硬碟目錄（Re'memor）：
- drives：每一顆硬碟（系統編號、名稱、格式、容量），拔掉後仍保留紀錄。
- folders：每個資料夾（含空資料夾）與它的總大小、檔案數。
- files：每個檔案（所有類型）的名稱、大小、日期與類型；照片與影片另外在 images 有詳細資料。
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 34  # v34：分類的說明與合併、我的關鍵字規則（可有年份範圍）、等本人選的資料夾、關鍵字統計；v33：自動分類（分類清單、本人設定、AI 建議、學到的規則、每個資料夾目前的分類）；v32：側邊欄「喜好項目」裡釘選的檔案與捷徑；v31：已經交給 Spotlight 的項目；v30：助理的對話紀錄；v29：硬碟健康（自我檢測、讀取錯誤、本人的處理方式）；v28：文件的語意向量（用意思找文件）；v27：助理提出的動作（提案、執行、復原的紀錄）；v26：佔比圖依資料夾找大檔案、加總小檔案的索引；v25：依副檔名找檔案的索引（要讀文字、要辨識的檔案）；v24：智慧資料夾（儲存的搜尋）；v23：文件文字與全文索引；v22：工作紀錄（關掉 App 再開仍然看得到）；v21：待刪除的標記；v20：完整內容指紋與資料夾簽章（重複項目）；v19：每個資料夾「主要是什麼類型」（佔比圖上色用）；v18：照片原有的顏色標籤帶到檔案目錄；v17：硬碟總覽的類型統計索引；v16：瀏覽用的索引、檔案與資料夾的顏色標籤（v15：硬碟目錄 drives、folders、files）

SCHEMA = """
CREATE TABLE IF NOT EXISTS roots (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_scan TEXT
);

-- v15：每一顆硬碟。key＝「uuid:系統編號」，查不到編號時用「vol:名稱|容量|格式」
CREATE TABLE IF NOT EXISTS drives (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    uuid TEXT,
    name TEXT NOT NULL,
    fs_type TEXT,
    capacity INTEGER,
    read_only INTEGER NOT NULL DEFAULT 0,
    mount_path TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    rel_path TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    fingerprint TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    taken_at TEXT,
    camera TEXT,
    lens TEXT,
    lat REAL,
    lon REAL,
    status TEXT NOT NULL DEFAULT 'ok',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    analyzed_at TEXT,
    model TEXT,
    description TEXT,
    tags TEXT,
    objects TEXT,
    scene TEXT,
    ocr_text TEXT,
    user_tags TEXT,
    note TEXT,
    error TEXT,
    search_text TEXT NOT NULL DEFAULT '',
    embedding BLOB,
    embed_model TEXT,
    UNIQUE (root_id, rel_path)
);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    cover_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY,
    name TEXT,
    cover_face_id INTEGER,
    hidden INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS faces (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    score REAL,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    manual INTEGER NOT NULL DEFAULT 0,
    excluded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_kv (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS smart_albums (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS album_items (
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (album_id, image_id)
);

-- v13：AI 向量（描述文字的語意向量 text、圖像搜尋 clip）獨立存放。
-- 放在 images 表裡時，每一次「掃一遍全部照片」的查詢都會連這些大資料一起讀，百萬張時會很慢。
CREATE TABLE IF NOT EXISTS image_vectors (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    model TEXT,
    vec BLOB NOT NULL,
    PRIMARY KEY (image_id, kind)
) WITHOUT ROWID;

-- v14：資料夾（和資料夾來源本身，path 為空）的收藏與拖曳排的順序；只影響顯示，不會動到硬碟
CREATE TABLE IF NOT EXISTS folder_prefs (
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0,
    position INTEGER,
    PRIMARY KEY (root_id, path)
);

-- v13：資料夾自訂封面（path 空字串＝資料夾來源本身）
CREATE TABLE IF NOT EXISTS folder_covers (
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    PRIMARY KEY (root_id, path)
);

-- v15：每個資料夾（path 空字串＝資料夾來源本身）。
-- files／bytes 是直接放在這層的檔案；total_files／total_bytes 含所有子資料夾。
-- scan_gen：這個資料夾在第幾次掃描時處理完成，掃描中斷後接著掃時用來跳過已完成的部分。
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    mtime REAL,
    scan_gen INTEGER NOT NULL DEFAULT 0,
    files INTEGER NOT NULL DEFAULT 0,
    bytes INTEGER NOT NULL DEFAULT 0,
    total_files INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    subfolders INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    label TEXT,
    main_kind TEXT,
    shape_sig TEXT,
    content_sig TEXT,
    UNIQUE (root_id, path)
);

-- v15：每個檔案（所有類型）。kind：photo／raw／video／audio／document／archive／package／other
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ext TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    ctime REAL,
    status TEXT NOT NULL DEFAULT 'ok',
    image_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    label TEXT,
    content_hash TEXT,
    hashed_at TEXT,
    UNIQUE (folder_id, name)
);
"""

# v21：待刪除。使用者在「重複項目」標記的多餘副本；只是標記，清理要另外由本人確認
PENDING_SCHEMA = """
CREATE TABLE IF NOT EXISTS delete_marks (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    sig TEXT NOT NULL,
    marked_at TEXT NOT NULL,
    UNIQUE (kind, item_id)
);

-- v31：已經交給 Mac 的 Spotlight 的項目（entity：file:編號／folder:編號／drive:…／smart:…；sig：內容摘要，變了才重送）
CREATE TABLE IF NOT EXISTS spotlight_sync (
    entity TEXT PRIMARY KEY,
    spot_id TEXT NOT NULL,
    sig TEXT NOT NULL,
    synced_at TEXT NOT NULL
);

-- v33：自動分類（只記在目錄裡，不改硬碟上的檔名或位置）。本人設定的和規則、AI 的分開存，本人的永遠優先。
CREATE TABLE IF NOT EXISTS categories (
    key TEXT PRIMARY KEY,
    name TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    builtin INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    examples TEXT,
    merged_into TEXT
);
-- v34：關鍵字規則（本人在關鍵字雲定的，或助理提出、本人確認的）。year_from／year_to：只套用在這幾年的資料夾
CREATE TABLE IF NOT EXISTS category_rules (
    id INTEGER PRIMARY KEY,
    pattern TEXT NOT NULL,
    category TEXT NOT NULL,
    year_from INTEGER,
    year_to INTEGER,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
);
-- v34：等本人選的資料夾（例如分類被拆開，本人原本手動設的那些不知道該跟到哪一類）
CREATE TABLE IF NOT EXISTS category_pending (
    folder_id INTEGER PRIMARY KEY REFERENCES folders(id) ON DELETE CASCADE,
    options TEXT NOT NULL,
    reason TEXT
);
-- v34：資料夾名稱與檔名裡常出現的詞（關鍵字雲）
CREATE TABLE IF NOT EXISTS keyword_stats (
    word TEXT PRIMARY KEY,
    folders INTEGER NOT NULL DEFAULT 0,
    files INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS category_user (
    target TEXT PRIMARY KEY,
    category TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS category_ai (
    folder_id INTEGER PRIMARY KEY REFERENCES folders(id) ON DELETE CASCADE,
    category TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT,
    sig TEXT,
    model TEXT,
    created_at TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS category_learned (
    token TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS folder_category (
    folder_id INTEGER PRIMARY KEY REFERENCES folders(id) ON DELETE CASCADE,
    category TEXT,
    source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT,
    review INTEGER NOT NULL DEFAULT 0,
    year INTEGER
);
CREATE INDEX IF NOT EXISTS idx_folder_category ON folder_category(category);
CREATE INDEX IF NOT EXISTS idx_folder_category_review ON folder_category(review) WHERE review = 1;

-- v32：側邊欄「喜好項目」裡釘選的檔案與捷徑（資料夾仍記在 folder_prefs）。只影響顯示，不動硬碟上的檔案。
-- kind：file＝檔案（href 會打開所在資料夾並選好它）／link＝側邊欄的其他項目（ref 是那一項的代號，例如 kind:photo、smart:3）
-- position 和 folder_prefs.position 共用同一組順序。
CREATE TABLE IF NOT EXISTS sidebar_links (
    href TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ref TEXT,
    name TEXT NOT NULL,
    icon TEXT,
    position INTEGER,
    created_at TEXT NOT NULL
);

-- v30：助理的對話紀錄（只存在這台電腦）。steps／sources／actions 是 JSON（actions 是動作提案的編號）
CREATE TABLE IF NOT EXISTS assistant_chats (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_messages (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL REFERENCES assistant_chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    steps TEXT,
    sources TEXT,
    actions TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_messages_chat ON assistant_messages(chat_id, id);

-- v29：硬碟健康。status：ok／warn／fail／unknown；decision：本人選的處理方式（pause／light／continue），
-- decided_level：做決定時的嚴重程度（狀況變糟時要再問一次）
CREATE TABLE IF NOT EXISTS drive_health (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    smart TEXT,
    findings TEXT,
    io_errors INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT,
    decision TEXT,
    decided_level INTEGER,
    decided_at TEXT
);

-- v28：文件的語意向量（用意思找、跨語言搜尋）。vec：調成長度 1 後壓成 8 位元整數
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    has_text INTEGER NOT NULL DEFAULT 0,
    vec BLOB NOT NULL
);

-- v27：助理提出的動作。助理只能建立提案（state＝proposed）；本人在畫面上確認後才執行，並記下復原需要的資料。
-- kind：label／smart_folder／mark_delete（只在目錄裡）、move／rename／to_pending（會改變硬碟上檔案的位置或名稱）
CREATE TABLE IF NOT EXISTS assistant_actions (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    level INTEGER NOT NULL,
    summary TEXT NOT NULL,
    payload TEXT NOT NULL,
    state TEXT NOT NULL,
    result TEXT,
    question TEXT,
    created_at TEXT NOT NULL,
    done_at TEXT,
    undone_at TEXT
);

-- v26：佔比圖：每個資料夾裡「大於某個大小」的檔案、以及小檔案的總和，只讀索引就能算
CREATE INDEX IF NOT EXISTS idx_files_folder_size ON files(folder_id, size) WHERE status = 'ok';

-- v25：依副檔名找檔案（要讀文字的文件、要辨識的圖片），一百萬個檔案也不用全部掃過
CREATE INDEX IF NOT EXISTS idx_files_ext ON files(lower(ext)) WHERE status = 'ok';

-- v24：智慧資料夾：儲存起來的搜尋條件（JSON）
CREATE TABLE IF NOT EXISTS smart_folders (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    position INTEGER,
    created_at TEXT NOT NULL
);

-- v23：文件文字（壓縮存放，用來顯示命中的段落）與全文索引（只存斷好的詞，不另存原文）
CREATE TABLE IF NOT EXISTS file_text (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    body BLOB,
    chars INTEGER NOT NULL DEFAULT 0,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    extracted_at TEXT NOT NULL,
    error TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(tokens, content = '', tokenize = 'unicode61 remove_diacritics 2');
-- v25：文件文字的狀態另外存一份索引：統計與比對「讀過之後有沒有改過」時不用讀到壓縮的內文
CREATE INDEX IF NOT EXISTS idx_file_text_state ON file_text(file_id, status, source, size, mtime);

-- v22：背景工作的紀錄。state：queued／running／done／stopped／interrupted／error
CREATE TABLE IF NOT EXISTS job_log (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    options TEXT,
    state TEXT NOT NULL,
    message TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
"""

# v15：roots 新增的欄位：所在硬碟、在硬碟裡的位置、掃描進度
ROOT_COLUMNS = [
    ("drive_id", "INTEGER REFERENCES drives(id) ON DELETE SET NULL"),
    ("drive_rel", "TEXT"),
    ("scan_gen", "INTEGER NOT NULL DEFAULT 0"),
    ("scan_state", "TEXT"),
]

CATALOG_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
-- v17：硬碟總覽「每顆硬碟各類型佔多少」只讀這個索引（也涵蓋原本依 root_id、status 的查詢）
DROP INDEX IF EXISTS idx_files_root_status;
CREATE INDEX IF NOT EXISTS idx_files_root_kind ON files(root_id, status, kind, size);
DROP INDEX IF EXISTS idx_files_kind;
-- 側邊欄「類型」的檔案數與總大小：只讀這個索引就能算完，不必讀整張表
CREATE INDEX IF NOT EXISTS idx_files_kind_size ON files(status, kind, size);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_image ON files(image_id);
-- v16：列表與圖像檢視只讀「看得到的那一段」，排序交給這些索引（不必把整個資料夾讀出來再排）
CREATE INDEX IF NOT EXISTS idx_files_folder_name ON files(folder_id, status, name COLLATE NOCASE);
-- 跨硬碟的類型篩選：依名稱、大小、日期排序時沿著索引走，邊走邊挑出要的類型
CREATE INDEX IF NOT EXISTS idx_files_all_name ON files(status, name COLLATE NOCASE, kind);
CREATE INDEX IF NOT EXISTS idx_files_all_size ON files(status, size, kind);
CREATE INDEX IF NOT EXISTS idx_files_all_mtime ON files(status, mtime, kind);
CREATE INDEX IF NOT EXISTS idx_files_label ON files(label) WHERE label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_folders_label ON folders(label) WHERE label IS NOT NULL;
-- v20：重複項目。完整內容指紋相同的檔案、簽章相同的資料夾
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash, size) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_folders_shape ON folders(shape_sig) WHERE shape_sig IS NOT NULL;
-- v28：列表上標出「別顆硬碟也有一模一樣的資料夾」
CREATE INDEX IF NOT EXISTS idx_folders_content ON folders(content_sig) WHERE content_sig IS NOT NULL;
-- 還沒比對內容的檔案：找「檔名與大小都相同」的待確認組別、算還要讀多少資料，都只讀這個索引
CREATE INDEX IF NOT EXISTS idx_files_unhashed ON files(size, name, root_id) WHERE content_hash IS NULL AND status = 'ok' AND size > 0;
"""

# v13：全文索引。中文、日文、韓文逐字＋兩字一組，其他文字依單字（可前綴比對）；
# 由觸發器自動和 images.search_text 同步（fts_tokens 是在 connect() 註冊的 Python 函式）。
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(tokens, tokenize = 'unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS images_fts_ins AFTER INSERT ON images BEGIN
    INSERT INTO search_fts(rowid, tokens) VALUES (new.id, fts_tokens(new.search_text));
END;
CREATE TRIGGER IF NOT EXISTS images_fts_upd AFTER UPDATE OF search_text ON images BEGIN
    DELETE FROM search_fts WHERE rowid = old.id;
    INSERT INTO search_fts(rowid, tokens) VALUES (new.id, fts_tokens(new.search_text));
END;
CREATE TRIGGER IF NOT EXISTS images_fts_del AFTER DELETE ON images BEGIN
    DELETE FROM search_fts WHERE rowid = old.id;
END;
-- 分析結果或檔案變了（模型欄位被清空）時，舊的向量一起刪掉
CREATE TRIGGER IF NOT EXISTS images_vec_text_reset AFTER UPDATE OF embed_model ON images WHEN new.embed_model IS NULL BEGIN
    DELETE FROM image_vectors WHERE image_id = new.id AND kind = 'text';
END;
CREATE TRIGGER IF NOT EXISTS images_vec_clip_reset AFTER UPDATE OF clip_model ON images WHEN new.clip_model IS NULL BEGIN
    DELETE FROM image_vectors WHERE image_id = new.id AND kind = 'clip';
END;
"""

_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]+")
_WORD = re.compile(r"[^\W_]+")


def fts_tokens(text: str | None) -> str:
    """全文索引用的詞：中日韓文字拆成單字與兩字一組（「海邊」→ 海 邊 海邊），其他保留原文交給 unicode61 斷詞。"""
    text = (text or "").lower()
    out: list[str] = []
    pos = 0
    for m in _CJK.finditer(text):
        out.append(text[pos:m.start()])
        run = m.group()
        out.extend(run)
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
        pos = m.end()
    out.append(text[pos:])
    return " ".join(x.strip() for x in out if x.strip())


def fts_query(term: str) -> str | None:
    """搜尋詞 → FTS5 查詢式；做不到和原本「子字串比對」一樣的結果時回傳 None（改用 LIKE）。"""
    t = (term or "").lower().strip()
    if not t:
        return None
    exprs: list[str] = []
    pos = 0
    pieces: list[tuple[bool, str]] = []
    for m in _CJK.finditer(t):
        pieces.append((False, t[pos:m.start()]))
        pieces.append((True, m.group()))
        pos = m.end()
    pieces.append((False, t[pos:]))
    for cjk, piece in pieces:
        if cjk:
            toks = [piece] if len(piece) == 1 else [piece[i:i + 2] for i in range(len(piece) - 1)]
            exprs += [f'"{x}"' for x in toks]
        else:
            words = _WORD.findall(piece)
            if not words:
                continue
            # 含數字的詞（檔名、型號，例如 0012、x-t5）常常從中間開始比對，交給 LIKE
            if any(ch.isdigit() for w in words for ch in w):
                return None
            exprs.append('"' + " ".join(words) + '"*')
    return "(" + " AND ".join(exprs) + ")" if exprs else None


# v2 新增欄位：(名稱, 型別定義)
V2_COLUMNS = [
    ("media_type", "TEXT NOT NULL DEFAULT 'photo'"),
    ("is_raw", "INTEGER NOT NULL DEFAULT 0"),
    ("folder", "TEXT NOT NULL DEFAULT ''"),
    ("sort_at", "TEXT"),
    ("tz_offset", "TEXT"),
    ("orientation", "INTEGER"),
    ("duration", "REAL"),
    ("fps", "REAL"),
    ("codec", "TEXT"),
    ("aperture", "REAL"),
    ("exposure_time", "REAL"),
    ("iso", "INTEGER"),
    ("focal_length", "REAL"),
    ("focal_35", "REAL"),
    ("altitude", "REAL"),
    ("rating", "INTEGER"),
    ("keywords", "TEXT"),
    ("title", "TEXT"),
    ("caption", "TEXT"),
    ("artist", "TEXT"),
    ("copyright", "TEXT"),
    ("software", "TEXT"),
    ("favorite", "INTEGER NOT NULL DEFAULT 0"),
    ("thumb_ok", "INTEGER NOT NULL DEFAULT 0"),
    ("faces_at", "TEXT"),
    ("faces_model", "TEXT"),
    ("clip", "BLOB"),
    ("clip_model", "TEXT"),
    ("place", "TEXT"),
    ("place_en", "TEXT"),
    ("country", "TEXT"),
    ("label", "TEXT"),
    ("stack_id", "INTEGER"),
    ("stack_top", "INTEGER NOT NULL DEFAULT 1"),
    ("phash", "TEXT"),
]

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_images_fingerprint ON images(fingerprint);
CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_sort ON images(sort_at);
CREATE INDEX IF NOT EXISTS idx_images_folder ON images(root_id, folder);
CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(favorite);
CREATE INDEX IF NOT EXISTS idx_album_items_image ON album_items(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_image ON faces(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_images_stack ON images(stack_id);
CREATE INDEX IF NOT EXISTS idx_images_root_status_sort ON images(root_id, status, sort_at);
CREATE INDEX IF NOT EXISTS idx_images_status_top_sort ON images(status, stack_top, sort_at);
CREATE INDEX IF NOT EXISTS idx_images_status_media ON images(status, media_type);
CREATE INDEX IF NOT EXISTS idx_images_status_size ON images(status, size);
"""

# 由掃描時的中繼資料寫入的欄位
META_FIELDS = (
    "width", "height", "taken_at", "tz_offset", "camera", "lens", "lat", "lon", "altitude",
    "orientation", "duration", "fps", "codec", "aperture", "exposure_time", "iso", "focal_length",
    "focal_35", "rating", "keywords", "title", "caption", "artist", "copyright", "software", "label",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def folder_of(rel_path: str) -> str:
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def _migrate_v34(conn: sqlite3.Connection) -> None:
    """v33 已經建好的分類表補上新欄位。"""
    for table, cols in (("categories", (("description", "TEXT"), ("examples", "TEXT"), ("merged_into", "TEXT"))),
                        ("category_ai", (("stale", "INTEGER NOT NULL DEFAULT 0"),)), ("folder_category", (("year", "INTEGER"),))):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(images)")}
    for name, ddl in V2_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE images ADD COLUMN {name} {ddl}")
    conn.executescript(INDEXES)
    root_cols = {row[1] for row in conn.execute("PRAGMA table_info(roots)")}
    for name, ddl in ROOT_COLUMNS:
        if name not in root_cols:
            conn.execute(f"ALTER TABLE roots ADD COLUMN {name} {ddl}")
    for table in ("files", "folders"):  # v16：顏色標籤（只存在目錄裡，不寫到硬碟）
        if "label" not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN label TEXT")
    if "main_kind" not in {r[1] for r in conn.execute("PRAGMA table_info(folders)")}:
        conn.execute("ALTER TABLE folders ADD COLUMN main_kind TEXT")
        from .catalog import update_folder_totals  # v19：替現有的資料夾補上「主要類型」

        for r in conn.execute("SELECT id FROM roots").fetchall():
            update_folder_totals(conn, r[0])
    conn.executescript(PENDING_SCHEMA)
    _migrate_v34(conn)
    # v20：完整內容指紋（要整個檔案讀過才有）與資料夾簽章
    file_cols = {r[1] for r in conn.execute("PRAGMA table_info(files)")}
    for name in ("content_hash", "hashed_at"):
        if name not in file_cols:
            conn.execute(f"ALTER TABLE files ADD COLUMN {name} TEXT")
    if "shape_sig" not in {r[1] for r in conn.execute("PRAGMA table_info(folders)")}:
        conn.execute("ALTER TABLE folders ADD COLUMN shape_sig TEXT")
        conn.execute("ALTER TABLE folders ADD COLUMN content_sig TEXT")
        from .dupes import update_folder_signatures

        for r in conn.execute("SELECT id FROM roots").fetchall():
            update_folder_signatures(conn, r[0])
    conn.executescript(CATALOG_INDEXES)
    # v18：照片原本就有的顏色標籤，帶到檔案目錄（之後兩邊一起更新）
    conn.execute("UPDATE files SET label = (SELECT i.label FROM images i WHERE i.id = files.image_id) "
                 "WHERE label IS NULL AND image_id IN (SELECT id FROM images WHERE label IS NOT NULL)")
    album_cols = {row[1] for row in conn.execute("PRAGMA table_info(albums)")}
    if "favorite" not in album_cols:
        conn.execute("ALTER TABLE albums ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
    if "position" not in album_cols:
        conn.execute("ALTER TABLE albums ADD COLUMN position INTEGER")
    person_cols = {row[1] for row in conn.execute("PRAGMA table_info(persons)")}
    if "groups" not in person_cols:
        conn.execute("ALTER TABLE persons ADD COLUMN groups TEXT")
    # v7：已存的「a;b;c」關鍵字拆成多個
    for row in conn.execute("SELECT id, keywords FROM images WHERE keywords LIKE '%;%'").fetchall():
        from .media import split_keywords

        fixed = split_keywords(json_list(row["keywords"]))
        conn.execute("UPDATE images SET keywords = ? WHERE id = ?", (json.dumps(fixed, ensure_ascii=False), row["id"]))
        refresh_search_text(conn, row["id"])
    # v10：有命名人物的照片重建搜尋索引，舊版本留下的索引可能沒有名字
    for row in conn.execute(
        "SELECT DISTINCT f.image_id FROM faces f JOIN persons p ON p.id = f.person_id WHERE p.name IS NOT NULL AND p.name != ''"
    ).fetchall():
        refresh_search_text(conn, row[0])
    if "folder" not in existing:  # 從 v1 升級：補齊資料夾與排序時間
        for row in conn.execute("SELECT id, rel_path, taken_at, mtime FROM images").fetchall():
            conn.execute(
                "UPDATE images SET folder = ?, sort_at = ? WHERE id = ?",
                (folder_of(row["rel_path"]), row["taken_at"] or local_iso(row["mtime"]), row["id"]),
            )


def _migrate_v13(conn: sqlite3.Connection) -> None:
    """向量搬到 image_vectors、建立全文索引。四萬張約數秒，只在升級時做一次。"""
    conn.execute(
        "INSERT OR REPLACE INTO image_vectors (image_id, kind, model, vec) "
        "SELECT id, 'text', embed_model, embedding FROM images WHERE embedding IS NOT NULL")
    conn.execute(
        "INSERT OR REPLACE INTO image_vectors (image_id, kind, model, vec) "
        "SELECT id, 'clip', clip_model, clip FROM images WHERE clip IS NOT NULL")
    conn.execute("UPDATE images SET embedding = NULL WHERE embedding IS NOT NULL")
    conn.execute("UPDATE images SET clip = NULL WHERE clip IS NOT NULL")
    # 沒有向量的就不算建立過，之後會重新建立
    conn.execute("UPDATE images SET embed_model = NULL WHERE embed_model IS NOT NULL AND id NOT IN "
                 "(SELECT image_id FROM image_vectors WHERE kind = 'text')")
    conn.execute("UPDATE images SET clip_model = NULL WHERE clip_model IS NOT NULL AND id NOT IN "
                 "(SELECT image_id FROM image_vectors WHERE kind = 'clip')")
    conn.executescript(FTS)
    conn.execute("DELETE FROM search_fts")
    conn.execute("INSERT INTO search_fts(rowid, tokens) SELECT id, fts_tokens(search_text) FROM images")


def local_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).replace(microsecond=0).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.create_function("fts_tokens", 1, fts_tokens, deterministic=True)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < SCHEMA_VERSION:
        conn.executescript(SCHEMA)
        _migrate(conn)
        if version < 13:
            _migrate_v13(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    return conn


def refresh_stats(conn: sqlite3.Connection) -> None:
    """更新資料庫對自己大小的估計（SQLite 用它決定查詢要走哪條路）。
    估計過時的時候，SQLite 可能挑到很慢的路（例如搜尋要幾十分鐘）。只取樣，一百萬個檔案約一秒。"""
    conn.execute("PRAGMA analysis_limit = 400")
    conn.execute("ANALYZE")
    conn.commit()


def json_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def build_search_text(row: dict) -> str:
    """所有可搜尋欄位合併成小寫字串；中文、英文、檔名都以子字串比對。"""
    parts = [
        row.get("rel_path") or "",
        row.get("description") or "",
        " ".join(json_list(row.get("tags"))),
        " ".join(json_list(row.get("user_tags"))),
        " ".join(json_list(row.get("objects"))),
        " ".join(json_list(row.get("keywords"))),
        row.get("scene") or "",
        row.get("ocr_text") or "",
        row.get("camera") or "",
        row.get("lens") or "",
        row.get("title") or "",
        row.get("caption") or "",
        row.get("note") or "",
        row.get("artist") or "",
        " ".join(row.get("people") or []),
        row.get("place") or "",
        row.get("place_en") or "",
        " ".join(row.get("country_names") or []),
    ]
    return "\n".join(p for p in parts if p).lower()


def refresh_search_text(conn: sqlite3.Connection, image_id: int) -> None:
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if row is not None:
        data = dict(row)
        people = conn.execute(
            "SELECT DISTINCT p.name, p.groups FROM faces f JOIN persons p ON p.id = f.person_id WHERE f.image_id = ?",
            (image_id,),
        ).fetchall()
        data["people"] = [p["name"] for p in people if p["name"]] + [g for p in people for g in json_list(p["groups"])]
        if data.get("country"):
            from .places import country_names

            data["country_names"] = list(country_names(data["country"]))
        conn.execute("UPDATE images SET search_text = ? WHERE id = ?", (build_search_text(data), image_id))


# ---- roots -----------------------------------------------------------------

def add_root(conn: sqlite3.Connection, path: str | Path, name: str | None = None) -> sqlite3.Row:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"資料夾不存在：{resolved}")
    name = (name or resolved.name or str(resolved)).strip()
    existing = conn.execute("SELECT * FROM roots WHERE name = ?", (name,)).fetchone()
    if existing:
        raise ValueError(f"名稱「{name}」已被使用（{existing['path']}），請換一個名稱")
    for row in conn.execute("SELECT * FROM roots"):
        other = Path(row["path"])
        if other == resolved or other in resolved.parents or resolved in other.parents:
            raise ValueError(f"與既有資料夾「{row['name']}」（{row['path']}）重疊")
    conn.execute("INSERT INTO roots (name, path, created_at) VALUES (?, ?, ?)", (name, str(resolved), now_iso()))
    conn.commit()
    return get_root(conn, name)


def get_root(conn: sqlite3.Connection, name_or_id) -> sqlite3.Row | None:
    if isinstance(name_or_id, int) or str(name_or_id).isdigit():
        row = conn.execute("SELECT * FROM roots WHERE id = ?", (int(name_or_id),)).fetchone()
        if row:
            return row
    return conn.execute("SELECT * FROM roots WHERE name = ?", (str(name_or_id),)).fetchone()


def list_roots(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT r.*,
                  (SELECT COUNT(*) FROM images i WHERE i.root_id = r.id AND i.status = 'ok') AS image_count
           FROM roots r ORDER BY r.name"""
    ).fetchall()


def relocate_root(conn: sqlite3.Connection, name_or_id, new_path: str | Path) -> sqlite3.Row:
    root = get_root(conn, name_or_id)
    if root is None:
        raise ValueError(f"找不到資料夾：{name_or_id}")
    resolved = Path(new_path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"資料夾不存在：{resolved}")
    conn.execute("UPDATE roots SET path = ? WHERE id = ?", (str(resolved), root["id"]))
    conn.commit()
    return get_root(conn, root["id"])


def remove_root(conn: sqlite3.Connection, name_or_id) -> int:
    root = get_root(conn, name_or_id)
    if root is None:
        raise ValueError(f"找不到資料夾：{name_or_id}")
    count = conn.execute("SELECT COUNT(*) FROM images WHERE root_id = ?", (root["id"],)).fetchone()[0]
    conn.execute("DELETE FROM roots WHERE id = ?", (root["id"],))
    conn.commit()
    return count


# ---- images ----------------------------------------------------------------

def absolute_path(conn: sqlite3.Connection, image) -> Path:
    root = conn.execute("SELECT path FROM roots WHERE id = ?", (image["root_id"],)).fetchone()
    return Path(root["path"]).joinpath(*image["rel_path"].split("/"))


def get_image(conn: sqlite3.Connection, image_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()


def set_user_fields(conn: sqlite3.Connection, image_id: int, user_tags=None, note=None, favorite=None) -> None:
    if user_tags is not None:
        clean: list[str] = []
        for tag in user_tags:
            tag = str(tag).strip()
            if tag and tag not in clean:
                clean.append(tag)
        conn.execute("UPDATE images SET user_tags = ? WHERE id = ?", (json.dumps(clean, ensure_ascii=False), image_id))
    if note is not None:
        conn.execute("UPDATE images SET note = ? WHERE id = ?", (str(note), image_id))
    if favorite is not None:
        conn.execute("UPDATE images SET favorite = ? WHERE id = ?", (1 if favorite else 0, image_id))
    if user_tags is not None or note is not None:
        conn.execute("UPDATE images SET embedding = NULL, embed_model = NULL WHERE id = ?", (image_id,))
        refresh_search_text(conn, image_id)
    conn.commit()


def stats(conn: sqlite3.Connection) -> dict:
    """圖庫的各種數量：images 表只掃一次（原本每個數字各掃一次，四萬張時每次要 0.2 秒）。"""
    row = conn.execute(
        """SELECT
             SUM(status = 'ok'),
             SUM(status = 'ok' AND media_type = 'photo'),
             SUM(status = 'ok' AND media_type = 'video'),
             SUM(status = 'missing'),
             SUM(status = 'ok' AND analyzed_at IS NOT NULL),
             SUM(status = 'ok' AND analyzed_at IS NULL AND error IS NULL),
             SUM(status = 'ok' AND analyzed_at IS NULL AND error IS NOT NULL),
             SUM(status = 'ok' AND embed_model IS NOT NULL),
             SUM(status = 'ok' AND favorite = 1),
             SUM(status = 'ok' AND media_type = 'photo' AND faces_at IS NULL),
             SUM(status = 'ok' AND clip_model IS NOT NULL)
           FROM images"""
    ).fetchone()
    v = [int(x or 0) for x in row]
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "roots": q("SELECT COUNT(*) FROM roots"),
        "images": v[0], "photos": v[1], "videos": v[2], "missing": v[3],
        "analyzed": v[4], "pending": v[5], "failed": v[6], "embedded": v[7], "favorites": v[8],
        "albums": q("SELECT COUNT(*) FROM albums"),
        "faces": q("SELECT COUNT(*) FROM faces"),
        "people": q("SELECT COUNT(*) FROM persons"),
        "faces_pending": v[9], "clip_done": v[10],
    }


# ---- albums ----------------------------------------------------------------

def create_album(conn: sqlite3.Connection, name: str, image_ids: list[int] | None = None) -> int:
    name = (name or "").strip() or "未命名相簿"
    now = now_iso()
    cur = conn.execute("INSERT INTO albums (name, created_at, updated_at) VALUES (?, ?, ?)", (name, now, now))
    album_id = cur.lastrowid
    if image_ids:
        add_to_album(conn, album_id, image_ids)
    conn.commit()
    return album_id


def add_to_album(conn: sqlite3.Connection, album_id: int, image_ids: list[int]) -> int:
    now = now_iso()
    cur = conn.executemany(
        "INSERT OR IGNORE INTO album_items (album_id, image_id, added_at) "
        "SELECT ?, id, ? FROM images WHERE id = ?",
        [(album_id, now, int(i)) for i in image_ids],
    )
    conn.execute("UPDATE albums SET updated_at = ? WHERE id = ?", (now, album_id))
    conn.commit()
    return cur.rowcount


def remove_from_album(conn: sqlite3.Connection, album_id: int, image_ids: list[int]) -> None:
    conn.executemany(
        "DELETE FROM album_items WHERE album_id = ? AND image_id = ?", [(album_id, int(i)) for i in image_ids]
    )
    conn.execute("UPDATE albums SET updated_at = ? WHERE id = ?", (now_iso(), album_id))
    conn.commit()


def list_albums(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT a.*,
                  COUNT(i.id) AS count,
                  MIN(i.sort_at) AS start_at,
                  MAX(i.sort_at) AS end_at,
                  COALESCE(a.cover_id, (
                      SELECT ai.image_id FROM album_items ai JOIN images x ON x.id = ai.image_id
                      WHERE ai.album_id = a.id AND x.status = 'ok' ORDER BY x.sort_at DESC LIMIT 1
                  )) AS cover
           FROM albums a
           LEFT JOIN album_items ai ON ai.album_id = a.id
           LEFT JOIN images i ON i.id = ai.image_id AND i.status = 'ok'
           GROUP BY a.id ORDER BY a.updated_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_album(conn: sqlite3.Connection, album_id: int) -> dict | None:
    for album in list_albums(conn):
        if album["id"] == album_id:
            return album
    return None


def update_album(conn: sqlite3.Connection, album_id: int, name=None, description=None, cover_id=None, favorite=None) -> None:
    if favorite is not None:
        conn.execute("UPDATE albums SET favorite = ? WHERE id = ?", (1 if favorite else 0, album_id))
    if name is not None:
        conn.execute("UPDATE albums SET name = ? WHERE id = ?", (name.strip() or "未命名相簿", album_id))
    if description is not None:
        conn.execute("UPDATE albums SET description = ? WHERE id = ?", (description, album_id))
    if cover_id is not None:
        # 0 或空字串＝改回自動（最新的照片）；只換封面不改變相簿的排列順序
        conn.execute("UPDATE albums SET cover_id = ? WHERE id = ?", (int(cover_id) or None, album_id))
    if name is not None or description is not None:
        conn.execute("UPDATE albums SET updated_at = ? WHERE id = ?", (now_iso(), album_id))
    conn.commit()


def delete_album(conn: sqlite3.Connection, album_id: int) -> None:
    conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
    conn.commit()
