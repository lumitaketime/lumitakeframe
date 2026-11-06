"""v13：AI 向量獨立的表、全文索引（FTS5）、資料夾封面。"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from lumilib import db
from lumilib import search as S


def _add(conn, root_id, rel, text, **extra):
    conn.execute(
        "INSERT INTO images (root_id, rel_path, size, mtime, fingerprint, status, first_seen, last_seen, folder, sort_at) "
        "VALUES (?, ?, 1, 0, ?, 'ok', '2024-01-01', '2024-01-01', ?, '2024-01-01T00:00:00')",
        (root_id, rel, rel, db.folder_of(rel)),
    )
    image_id = conn.execute("SELECT id FROM images WHERE rel_path = ?", (rel,)).fetchone()[0]
    sets = {"description": text, **extra}
    conn.execute(f"UPDATE images SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), image_id))
    db.refresh_search_text(conn, image_id)
    conn.commit()
    return image_id


class FtsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "p").mkdir()
        self.conn = db.connect(self.tmp / "lib.db")
        self.root = db.add_root(self.conn, self.tmp / "p")["id"]
        self.a = _add(self.conn, self.root, "2024/DSCF0012.jpg", "海邊的夕陽，一隻小貓坐在沙灘上")
        self.b = _add(self.conn, self.root, "2024/IMG_1.jpg", "Kittens playing in the café garden")
        self.c = _add(self.conn, self.root, "trip/x.jpg", "台北街頭 neon lights")

    def tearDown(self):
        self.conn.close()

    def ids(self, q):
        return {r["id"] for r in S.search(self.conn, q, limit=100)["results"]}

    def test_tokens_and_query(self):
        self.assertEqual(db.fts_tokens("海邊 Cat"), "海 邊 海邊 cat")
        self.assertEqual(db.fts_query("海邊"), '("海邊")')
        self.assertEqual(db.fts_query("貓"), '("貓")')
        self.assertEqual(db.fts_query("沙灘上"), '("沙灘" AND "灘上")')
        self.assertEqual(db.fts_query("kit"), '("kit"*)')
        self.assertIsNone(db.fts_query("0012"))  # 含數字：逐筆比對，才找得到檔名中間的數字

    def test_search_matches_substring_behaviour(self):
        self.assertEqual(self.ids("小貓"), {self.a})
        self.assertEqual(self.ids("貓"), {self.a})
        self.assertEqual(self.ids("kitten"), {self.b})
        self.assertEqual(self.ids("cafe"), {self.b})  # 去掉重音符號
        self.assertEqual(self.ids("0012"), {self.a})
        self.assertEqual(self.ids("台北 neon"), {self.c})
        self.assertEqual(self.ids("海邊 -貓"), set())
        self.assertEqual(self.ids("folder:trip 街頭"), {self.c})

    def test_index_follows_changes(self):
        db.set_user_fields(self.conn, self.c, user_tags=["夜景"])
        self.assertEqual(self.ids("夜景"), {self.c})
        self.conn.execute("DELETE FROM images WHERE id = ?", (self.c,))
        self.conn.commit()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM search_fts WHERE rowid = ?", (self.c,)).fetchone()[0], 0)

    def test_vector_reset_trigger(self):
        vec = np.ones(4, dtype=np.float32).tobytes()
        self.conn.execute("INSERT INTO image_vectors VALUES (?, 'clip', 'm', ?)", (self.a, vec))
        self.conn.execute("INSERT INTO image_vectors VALUES (?, 'text', 'e', ?)", (self.a, vec))
        self.conn.execute("UPDATE images SET clip_model = 'm', embed_model = 'e' WHERE id = ?", (self.a,))
        self.conn.execute("UPDATE images SET clip_model = NULL WHERE id = ?", (self.a,))
        kinds = {r[0] for r in self.conn.execute("SELECT kind FROM image_vectors WHERE image_id = ?", (self.a,))}
        self.assertEqual(kinds, {"text"})
        self.conn.execute("DELETE FROM images WHERE id = ?", (self.a,))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM image_vectors").fetchone()[0], 0)


class MigrationV13Tests(unittest.TestCase):
    def test_vectors_move_out_and_fts_is_built(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "p").mkdir()
        conn = db.connect(tmp / "lib.db")
        root = db.add_root(conn, tmp / "p")["id"]
        a = _add(conn, root, "a.jpg", "婚禮 會場")
        b = _add(conn, root, "b.jpg", "street")
        # 模擬 v12 的資料：向量在 images 表裡、還沒有全文索引
        vec = np.arange(4, dtype=np.float32).tobytes()
        conn.execute("UPDATE images SET clip = ?, clip_model = 'm', embedding = ?, embed_model = 'e' WHERE id = ?", (vec, vec, a))
        conn.execute("UPDATE images SET clip_model = 'm' WHERE id = ?", (b,))  # 有標記但沒有向量
        conn.execute("DELETE FROM image_vectors")
        conn.executescript("DROP TABLE search_fts; PRAGMA user_version = 12;")
        conn.commit()
        conn.close()

        conn = db.connect(tmp / "lib.db")
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        rows = {(r["image_id"], r["kind"], r["model"]) for r in conn.execute("SELECT * FROM image_vectors")}
        self.assertEqual(rows, {(a, "clip", "m"), (a, "text", "e")})
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM images WHERE clip IS NOT NULL OR embedding IS NOT NULL").fetchone()[0], 0)
        self.assertIsNone(conn.execute("SELECT clip_model FROM images WHERE id = ?", (b,)).fetchone()[0])  # 會重新建立
        self.assertEqual({r["id"] for r in S.search(conn, "婚禮")["results"]}, {a})
        conn.close()


class FolderCoverTests(unittest.TestCase):
    def test_cover_override(self):
        from fastapi.testclient import TestClient

        from lumilib.config import load_config
        from lumilib.server import create_app

        tmp = Path(tempfile.mkdtemp())
        (tmp / "p").mkdir()
        cfg = load_config(tmp / "home")
        conn = db.connect(cfg.db_path)
        root = db.add_root(conn, tmp / "p")["id"]
        conn.execute("UPDATE images SET thumb_ok = 1")
        a = _add(conn, root, "trip/day1/a.jpg", "a", thumb_ok=1)
        b = _add(conn, root, "trip/day2/b.jpg", "b", thumb_ok=1, sort_at="2025-01-01T00:00:00")
        conn.close()
        with TestClient(create_app(cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1)) as c:
            top = c.get("/api/folders", params={"root": root}).json()
            self.assertEqual(top["folders"][0]["cover"], b)  # 預設：最新的照片
            r = c.post("/api/folders/cover", json={"root_id": root, "path": "trip", "image_id": a})
            self.assertEqual(r.status_code, 200)
            top = c.get("/api/folders", params={"root": root}).json()
            self.assertEqual((top["folders"][0]["cover"], top["folders"][0]["cover_custom"]), (a, True))
            inside = c.get("/api/folders", params={"root": root, "path": "trip"}).json()
            self.assertEqual((inside["cover"], inside["cover_custom"]), (a, True))
            # 來源本身的封面
            c.post("/api/folders/cover", json={"root_id": root, "path": "", "image_id": a})
            self.assertEqual(c.get("/api/folders").json()["roots"][0]["cover"], a)
            # 改回自動
            c.post("/api/folders/cover", json={"root_id": root, "path": "trip", "image_id": None})
            top = c.get("/api/folders", params={"root": root}).json()
            self.assertEqual((top["folders"][0]["cover"], top["folders"][0]["cover_custom"]), (b, False))
            # 相簿：設定與改回自動，不會改變相簿的排列順序
            album = c.post("/api/albums", json={"name": "x", "ids": [a, b]}).json()
            c.post(f"/api/albums/{album['id']}", json={"cover_id": a})
            self.assertEqual(c.get(f"/api/albums/{album['id']}").json()["cover"], a)
            c.post(f"/api/albums/{album['id']}", json={"cover_id": 0})
            self.assertEqual(c.get(f"/api/albums/{album['id']}").json()["cover"], b)


if __name__ == "__main__":
    unittest.main()
