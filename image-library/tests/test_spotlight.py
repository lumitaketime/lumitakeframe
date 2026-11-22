"""Spotlight 的項目清單：硬碟（包括沒接上的）與智慧資料夾；id 就是要打開的頁面。"""

import shutil

from lumilib import db
from lumilib.find import save_smart_folder
from lumilib.scanner import scan_all
from lumilib.spotlight import payload

from test_catalog import CatalogTestCase


class SpotlightTests(CatalogTestCase):
    def test_items(self):
        d = self.tmp / "備份碟 3"
        d.mkdir()
        (d / "a.txt").write_text("x", encoding="utf-8")
        db.add_root(self.conn, d, "備份碟 3")
        scan_all(self.conn, self.cfg)
        save_smart_folder(self.conn, "預算文件", {"q": "預算 表", "kind": "document"})
        p = payload(self.conn)
        titles = {i["title"]: i for i in p["items"]}
        drive = next(i for i in p["items"] if i["type"] == "public.volume")
        self.assertTrue(drive["path"].startswith("/folders/"))
        self.assertEqual(drive["id"], "rememor:" + drive["path"])
        self.assertIn("已接上", drive["description"])
        smart = titles["預算文件"]
        self.assertIn("smart=", smart["path"])
        self.assertNotIn("'", smart["path"])  # 外殼用 JavaScript 字串打開頁面：網址裡不能有單引號
        v1 = p["version"]
        shutil.rmtree(d)
        p2 = payload(self.conn)
        self.assertIn("沒接上", next(i for i in p2["items"] if i["type"] == "public.volume")["description"])  # 拔掉之後還在
        self.assertNotEqual(p2["version"], v1)
        self.assertEqual(payload(self.conn, enabled=False), {"enabled": False, "version": "off", "items": []})


class SpotlightReportTests(CatalogTestCase):
    def test_report_is_shown(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            self.assertIsNone(c.get("/api/spotlight/status").json()["report"])
            c.post("/api/spotlight/report", json={"ok": False, "count": 0, "error": "測試錯誤"})
            r = c.get("/api/spotlight/status").json()["report"]
            self.assertEqual((r["ok"], r["error"]), (False, "測試錯誤"))
            self.assertIsNone(r["probe"])
            c.post("/api/spotlight/report", json={"ok": True, "count": 12, "error": "", "probe": 5, "probe_error": ""})
            r = c.get("/api/spotlight/status").json()["report"]
            self.assertEqual((r["ok"], r["count"], r["probe"]), (True, 12, 5))  # 自我檢查：Spotlight 自己找得到
            self.assertIn("total", c.get("/api/spotlight/status").json())


class SpotlightSyncTests(CatalogTestCase):
    """外接硬碟的資料夾與檔案：第一次全部交給 Spotlight，之後只交有變動的；不在了的拿掉；內建磁碟的不放。"""

    def run_pass(self, enabled=True, limit=500, internal=True):
        from lumilib import spotlight

        upsert, delete, cursor, reset = [], [], "", False
        while True:
            out = spotlight.changes(self.conn, cursor, limit, enabled, internal)
            reset = reset or out["reset"]
            upsert += out["upsert"]
            delete += out["delete"]
            spotlight.ack(self.conn, [{"entity": u["entity"], "id": u["id"], "sig": u["sig"]} for u in out["upsert"]],
                          [d["entity"] for d in out["delete"] if d["entity"]])
            cursor = out["cursor"]
            if not cursor:
                return upsert, delete, reset

    def test_delta_sync(self):
        from unittest import mock

        from lumilib import spotlight, textindex

        ext = self.tmp / "外接" / "備份碟 3"
        (ext / "國中").mkdir(parents=True)
        (ext / "國中" / "寄居蟹報告.txt").write_text("觀察寄居蟹換殼", encoding="utf-8")
        (ext / "a.txt").write_text("x", encoding="utf-8")
        inside = self.tmp / "內建"
        inside.mkdir()
        (inside / "b.txt").write_text("y", encoding="utf-8")
        db.add_root(self.conn, ext, "備份碟 3")
        db.add_root(self.conn, inside, "內建")
        scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)
        # 測試裡沒有 /Volumes：把「外接」當成外接硬碟的位置
        with mock.patch.object(spotlight, "EXTERNAL_PREFIX", str(self.tmp / "外接") + "/"):
            spotlight.changed()
            upsert, delete, _ = self.run_pass(limit=1, internal=False)  # 每批只看一筆：分批也要正確
            titles = {u["title"]: u for u in upsert}
            self.assertIn("寄居蟹報告.txt", titles)
            self.assertIn("國中", titles)
            self.assertNotIn("b.txt", titles)  # 設定成只放外接硬碟：內建磁碟的不放
            spotlight.changed()
            upsert, delete, _ = self.run_pass()  # 預設：內建磁碟的也放（和 Re'memor 的搜尋找得到的一樣）
            self.assertEqual([u["title"] for u in upsert], ["b.txt"])
            self.assertEqual(spotlight.total(self.conn), self.conn.execute("SELECT COUNT(*) FROM spotlight_sync").fetchone()[0])  # 全部放好了
            self.assertEqual(delete, [])
            spotlight.changed()
            upsert, delete, _ = self.run_pass(internal=False)  # 再關掉：內建磁碟的拿掉
            self.assertEqual(upsert, [])
            self.assertTrue(any(d["id"].endswith("select=b.txt") for d in delete))
            report = titles["寄居蟹報告.txt"]
            self.assertIn("寄居蟹換殼", report["text"])  # 文件內容一起放
            self.assertIn("select=", report["id"])
            self.assertEqual(report["type"], "public.plain-text")  # 確切的類型：Spotlight 才會歸到「文件」
            self.assertNotIn("'", report["id"])

            self.assertEqual(self.run_pass(internal=False), ([], [], False))  # 沒有變動：什麼都不送
            spotlight.changed()
            self.assertEqual(self.run_pass(internal=False)[:2], ([], []))  # 比對一輪，內容都一樣

            (ext / "a.txt").unlink()
            scan_all(self.conn, self.cfg)
            spotlight.changed()
            upsert, delete, _ = self.run_pass(internal=False)
            self.assertTrue(any(d["id"].endswith("select=a.txt") for d in delete))  # 不在了的拿掉

            _, _, reset = self.run_pass(enabled=False)  # 關掉：全部拿掉
            self.assertTrue(reset)
            self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM spotlight_sync").fetchone()[0], 0)

    def test_position_for_select(self):
        from lumilib.catalog import item_position

        d = self.tmp / "碟"
        (d / "子資料夾").mkdir(parents=True)
        for n in ("c.txt", "a.txt", "b.txt"):
            (d / n).write_text(n, encoding="utf-8")
        db.add_root(self.conn, d, "碟")
        scan_all(self.conn, self.cfg)
        rid = self.conn.execute("SELECT id FROM roots").fetchone()[0]
        self.assertEqual(item_position(self.conn, rid, "", "子資料夾"), 0)  # 資料夾在前
        self.assertEqual(item_position(self.conn, rid, "", "b.txt"), 2)
        self.assertEqual(item_position(self.conn, rid, "", "b.txt", desc=True), 2)
        self.assertEqual(item_position(self.conn, rid, "", "c.txt", desc=True), 1)
        self.assertIsNone(item_position(self.conn, rid, "", "沒有這個"))
