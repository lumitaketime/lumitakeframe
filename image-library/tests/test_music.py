"""音樂資訊：讀出曲名、演出者、專輯，搜歌名或歌手找得到；舊 MP3 的 Big5 標籤還原成中文；不修改檔案。"""

from pathlib import Path

from lumilib import db, music, textindex
from lumilib.find import find
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def mp3(path: Path, **frames) -> None:
    """做一個很短的 MP3（幾個靜音的音框）並寫入 ID3 標籤。"""
    from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK

    header = bytes([0xFF, 0xFB, 0x90, 0x64])  # MPEG-1 Layer III、128 kbps、44.1 kHz
    path.write_bytes((header + bytes(413)) * 20)
    tag = ID3()
    cls = {"title": TIT2, "artist": TPE1, "album": TALB, "track": TRCK}
    for k, (text, enc) in frames.items():
        tag.add(cls[k](encoding=enc, text=text))
    tag.save(str(path))


class MusicTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "音樂碟"
        d.mkdir()
        mp3(d / "01.mp3", title=("晴天", 3), artist=("周杰倫", 3), album=("葉惠美", 3), track=("1/11", 3))
        # 舊軟體寫的標籤：Big5 的位元組被當成 Latin-1 存起來
        mp3(d / "02.mp3", title=("月亮代表我的心".encode("cp950").decode("latin-1"), 0), artist=("鄧麗君".encode("cp950").decode("latin-1"), 0))
        (d / "壞掉.mp3").write_bytes(b"not audio at all")
        db.add_root(self.conn, d, "音樂碟")
        scan_all(self.conn, self.cfg)
        self.before = {p.name: p.stat().st_mtime for p in d.iterdir()}

    def test_reads_tags_and_searches(self):
        r = textindex.run_extract(self.conn)
        self.assertEqual(r.music, 2)
        self.assertEqual({p.name: p.stat().st_mtime for p in self.drive.iterdir()}, self.before)  # 沒有修改檔案
        fid = self.conn.execute("SELECT id FROM files WHERE name = '01.mp3'").fetchone()[0]
        info = music.parse(textindex.body(self.conn, fid))
        self.assertEqual((info["曲名"], info["演出者"], info["專輯"], info["曲目"]), ("晴天", "周杰倫", "葉惠美", "1"))
        self.assertIn("長度", info)
        res = find(self.conn, "周杰倫")
        self.assertEqual(res["items"][0]["name"], "01.mp3")
        self.assertEqual(res["items"][0]["match"], "music")
        self.assertIn("演出者", "".join(p["text"] for p in res["items"][0]["snippet"]))
        self.assertEqual(find(self.conn, "鄧麗君")["items"][0]["name"], "02.mp3")  # Big5 還原

    def test_fix_text(self):
        self.assertEqual(music.fix_text("Hello"), "Hello")
        self.assertEqual(music.fix_text("晴天"), "晴天")
        self.assertEqual(music.fix_text("鄧麗君".encode("cp950").decode("latin-1")), "鄧麗君")
        self.assertEqual(music.fix_text("Beyoncé"), "Beyoncé")  # 真的西歐文字不動
        self.assertEqual(music.fix_text("Röyksopp"), "Röyksopp")
