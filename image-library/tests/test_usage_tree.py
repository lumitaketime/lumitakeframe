"""佔比圖：一路拆到每個資料夾與檔案；太小的合併成「其他」，可以列出裡面有什麼。"""

import unittest

from lumilib import db
from lumilib.scanner import scan_all
from lumilib.usage import FILE, FOLDER, REST, usage_rest, usage_tree

from test_catalog import CatalogTestCase


class UsageTreeTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "影音碟"
        (d / "影片" / "2015 畢業旅行").mkdir(parents=True)
        (d / "文件").mkdir()
        (d / "影片" / "2015 畢業旅行" / "大檔.mp4").write_bytes(b"x" * 600_000)
        (d / "影片" / "片頭.mp4").write_bytes(b"x" * 200_000)
        (d / "文件" / "報告.pdf").write_bytes(b"x" * 150_000)
        for i in range(30):
            (d / "文件" / f"小檔{i}.txt").write_bytes(b"x" * 100)
        self.root = db.add_root(self.conn, d, "影音碟")
        scan_all(self.conn, self.cfg)

    def rows(self, data):
        n = data["nodes"]
        return [dict(zip(n, vals)) for vals in zip(*n.values())]

    def test_every_folder_and_file_down_to_the_smallest_visible(self):
        data = usage_tree(self.conn, self.root["id"], "", px=10_000)
        rows = self.rows(data)
        self.assertEqual(rows[0]["type"], FOLDER)
        names = {r["name"]: r for r in rows}
        self.assertEqual(names["大檔.mp4"]["type"], FILE)  # 第三層的檔案也有自己的一塊
        self.assertEqual(rows[names["大檔.mp4"]["parent"]]["name"], "2015 畢業旅行")
        self.assertEqual(names["報告.pdf"]["bytes"], 150_000)
        rest = [r for r in rows if r["type"] == REST]
        self.assertEqual(len(rest), 1)  # 30 個小檔太小，合併成一塊「其他」
        self.assertEqual((rest[0]["name"], rest[0]["bytes"]), ("30", 3_000))
        listed = usage_rest(self.conn, rest[0]["id"], data["least"])
        self.assertEqual((listed["total"], len(listed["items"])), (30, 30))
        self.assertTrue(all(i["type"] == "file" and i["path"].startswith("文件/") for i in listed["items"]))
        # 每一層的大小加起來等於上一層
        for r in rows:
            if r["type"] == FOLDER and any(c["parent"] == rows.index(r) for c in rows):
                kids = sum(c["bytes"] for c in rows if c["parent"] == rows.index(r))
                self.assertEqual(kids, r["bytes"], r["name"])

    def test_node_budget_and_subfolder(self):
        data = usage_tree(self.conn, self.root["id"], "影片", px=10_000)
        self.assertEqual(data["name"], "影片")
        self.assertIn("大檔.mp4", data["nodes"]["name"])
        small = usage_tree(self.conn, self.root["id"], "", px=10_000, max_nodes=3)
        self.assertLessEqual(len(small["nodes"]["parent"]), 3 + 4)  # 超過上限就不再往下拆
        self.assertIsNone(usage_tree(self.conn, self.root["id"], "沒有這個"))


if __name__ == "__main__":
    unittest.main()
