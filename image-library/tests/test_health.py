"""硬碟健康：有狀況就先不碰那顆硬碟，等本人決定；讀取錯誤太多也立刻停下來再問。其他硬碟照常。"""

import errno
from unittest import mock

from lumilib import db, health, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase

OK = {"smart": "Verified", "attrs": {}}
BAD = {"smart": "Verified", "attrs": {"reallocated": 8, "pending": 3}}
FAILING = {"smart": "Failing", "attrs": {}}


class HealthTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        for name in ("好硬碟", "老硬碟"):
            d = self.tmp / name
            d.mkdir()
            (d / "筆記.txt").write_text(f"{name} 的內容", encoding="utf-8")
            db.add_root(self.conn, d, name)
        scan_all(self.conn, self.cfg)
        # 測試時兩個資料夾在同一顆磁碟上；當成兩顆不同的硬碟
        self.conn.execute("UPDATE roots SET drive_id = NULL")
        self.conn.commit()
        self.roots = {r["name"]: r for r in self.conn.execute("SELECT * FROM roots")}

    def reader(self, mapping):
        return lambda path: mapping.get(path.rsplit("/", 1)[-1], OK)

    def test_assess(self):
        self.assertEqual(health.assess("Verified", {}, 0)[0], "ok")
        self.assertEqual(health.assess("Not Supported", {}, 0)[0], "unknown")  # USB 外接盒多半讀不到：不擋
        self.assertEqual(health.assess(None, {"reallocated": 3}, 0)[0], "warn")
        self.assertEqual(health.assess(None, {"reallocated": 300}, 0)[0], "fail")
        self.assertEqual(health.assess("Failing", {}, 0)[0], "fail")
        self.assertEqual(health.assess("Verified", {"crc": 5}, 0)[0], "ok")  # 線材問題只提醒，不擋
        self.assertEqual(health.assess("Not Supported", {}, 12)[0], "warn")
        status, found = health.assess(None, {"pending": 4}, 0)
        self.assertIn("讀不穩定", found[0]["text"])

    def test_hold_until_the_user_decides(self):
        reader = self.reader({"老硬碟": BAD})
        hold = health.held_roots(self.conn, "scan", reader)
        self.assertEqual(hold, {self.roots["老硬碟"]["id"]})  # 有狀況的先不碰；好硬碟照常
        alerts = health.alerts(self.conn)
        self.assertEqual([a["name"] for a in alerts], ["老硬碟"])
        self.assertEqual(alerts[0]["status"], "warn")

        results = {r.root: r for r in scan_all(self.conn, self.cfg, hold=hold)}
        self.assertTrue(results["老硬碟"].held)
        self.assertFalse(results["好硬碟"].held)

        key = alerts[0]["key"]
        health.decide(self.conn, key, "light")  # 只記錄檔名、不讀內容
        self.assertEqual(health.held_roots(self.conn, "scan", reader), set())
        self.assertEqual(health.held_roots(self.conn, "read", reader), {self.roots["老硬碟"]["id"]})
        self.assertEqual(health.alerts(self.conn), [])
        health.decide(self.conn, key, "pause")
        self.assertEqual(health.held_roots(self.conn, "scan", reader), {self.roots["老硬碟"]["id"]})
        health.decide(self.conn, key, "continue")
        self.assertEqual(health.held_roots(self.conn, "read", reader), set())

        # 狀況變糟：再問一次
        health.check(self.conn, self.roots["老硬碟"], force=True, reader=self.reader({"老硬碟": FAILING}))
        self.assertEqual([a["status"] for a in health.alerts(self.conn)], ["fail"])
        self.assertEqual(health.held_roots(self.conn, "read", reader), {self.roots["老硬碟"]["id"]})

    def test_read_jobs_skip_held_drives(self):
        hold = {self.roots["老硬碟"]["id"]}
        r = textindex.run_extract(self.conn, hold=hold)
        self.assertEqual(r.read, 1)
        self.assertEqual(r.held, ["老硬碟"])
        self.assertIn("等你決定", textindex.describe(r))

    def test_io_errors_stop_the_drive_and_ask(self):
        with mock.patch.object(textindex, "extract", side_effect=OSError(errno.EIO, "Input/output error")):
            # 每個硬碟只有一份文件：先在老硬碟上累積到門檻前一次
            rid = self.roots["老硬碟"]["id"]
            for _ in range(health.IO_WARN - 1):
                self.assertFalse(health.io_error(self.conn, rid, OSError(errno.EIO, "x")))
            self.assertFalse(health.io_error(self.conn, rid, OSError(errno.ENOENT, "x")))  # 不是讀取錯誤：不算
            r = textindex.run_extract(self.conn)
        self.assertIn("老硬碟", r.held)
        alerts = health.alerts(self.conn)
        self.assertEqual([a["name"] for a in alerts], ["老硬碟"])
        self.assertIn("讀取錯誤", alerts[0]["findings"][-1]["text"])

    def test_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        rid = self.roots["老硬碟"]["id"]
        for _ in range(health.IO_WARN):
            health.io_error(self.conn, rid, OSError(errno.EIO, "x"))
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            alerts = c.get("/api/server").json()["health_alerts"]
            self.assertEqual(alerts[0]["name"], "老硬碟")
            listing = {h["name"]: h for h in c.get("/api/health").json()}
            self.assertEqual(listing["老硬碟"]["status"], "warn")
            self.assertEqual(c.post("/api/health/decide", json={"key": alerts[0]["key"], "decision": "nope"}).status_code, 400)
            out = c.post("/api/health/decide", json={"key": alerts[0]["key"], "decision": "pause"}).json()
            self.assertEqual(out["decision"], "pause")
            self.assertEqual(c.get("/api/server").json()["health_alerts"], [])
