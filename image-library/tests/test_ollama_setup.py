"""一鍵安裝 Ollama、Qwen 3.8 推薦、實測比較。

安裝流程不真的連網，也不呼叫 macOS 的 codesign／hdiutil：下載用本機假的網址，指令用假的 run。
"""

import io
import plistlib
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from subprocess import CompletedProcess

from PIL import Image

from lumilib import compare_models, db, ollama_setup
from lumilib.analyzer import _pull_error
from lumilib.models import recommend, recommend_assistant
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def fake_zip(name="Ollama", version="0.40.1") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Ollama.app/Contents/Info.plist", plistlib.dumps({"CFBundleName": name, "CFBundleShortVersionString": version}))
        z.writestr("Ollama.app/Contents/MacOS/Ollama", b"#!" + b"x" * 4096)
    return buf.getvalue()


class FakeResp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeRun:
    """模擬 ditto／codesign／open：記下呼叫過的指令。"""

    def __init__(self, signed=True):
        self.calls = []
        self.signed = signed

    def __call__(self, cmd, timeout=300):
        self.calls.append(cmd)
        if cmd[0] == "ditto" and cmd[1] == "-x":
            with zipfile.ZipFile(cmd[3]) as z:
                z.extractall(cmd[4])
        elif cmd[0] == "ditto":
            shutil.copytree(cmd[1], cmd[2])
        elif cmd[:2] == ["codesign", "--verify"]:
            return CompletedProcess(cmd, 0 if self.signed else 1, "", "" if self.signed else "invalid signature")
        elif cmd[:2] == ["codesign", "-dv"]:
            return CompletedProcess(cmd, 0, "", "Authority=Developer ID Application: Ollama Inc (ABCDE12345)\nTeamIdentifier=ABCDE12345\n")
        return CompletedProcess(cmd, 0, "", "")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.apps = self.tmp / "Applications"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, data, run=None, urls=("https://example.invalid/Ollama-darwin.zip",), trash=None):
        steps = []
        run = run or FakeRun()
        res = ollama_setup.install(self.tmp / "home", "http://127.0.0.1:1", lambda s, d, t: steps.append(s), urls=urls, run=run,
                                   opener=lambda req, timeout: FakeResp(data), apps_dir=self.apps, trash=trash or (lambda p: shutil.rmtree(p)),
                                   wait=lambda url, s, stop: True)
        return res, steps, run

    def test_installs_verified_app_and_opens_it(self):
        res, steps, run = self.install(fake_zip())
        self.assertTrue((self.apps / "Ollama.app" / "Contents" / "Info.plist").exists())
        self.assertEqual(res["version"], "0.40.1")
        self.assertFalse(res["updated"])
        self.assertTrue(res["ready"])
        self.assertIn(["open", str(self.apps / "Ollama.app")], run.calls)
        self.assertEqual([s for s in dict.fromkeys(steps)], ["download", "verify", "install", "open"])
        self.assertFalse((self.tmp / "home" / "tmp" / "ollama-install").exists())  # 暫存檔清掉了

    def test_refuses_unsigned_app(self):
        with self.assertRaises(ollama_setup.InstallError):
            self.install(fake_zip(), run=FakeRun(signed=False))
        self.assertFalse((self.apps / "Ollama.app").exists())

    def test_refuses_app_that_is_not_ollama(self):
        with self.assertRaises(ollama_setup.InstallError):
            self.install(fake_zip(name="Something"))
        self.assertFalse((self.apps / "Ollama.app").exists())

    def test_update_moves_old_version_to_trash(self):
        self.install(fake_zip(version="0.30.0"))
        trashed = []
        res, _, run = self.install(fake_zip(version="0.40.1"), trash=lambda p: (trashed.append(p), shutil.rmtree(p)))
        self.assertEqual(trashed, [self.apps / "Ollama.app"])
        self.assertEqual(ollama_setup.app_version(self.apps / "Ollama.app"), "0.40.1")
        self.assertTrue(any(c[0] == "osascript" for c in run.calls))  # 先請舊版結束

    def test_falls_back_to_next_url(self):
        tried = []

        def opener(req, timeout):
            tried.append(req.full_url)
            if "first" in req.full_url:
                raise OSError("unreachable")
            return FakeResp(fake_zip())

        res = ollama_setup.install(self.tmp / "home", "http://127.0.0.1:1", None, urls=("https://first.invalid/a.zip", "https://second.invalid/b.zip"),
                                   run=FakeRun(), opener=opener, apps_dir=self.apps, wait=lambda *a: True)
        self.assertEqual(len(tried), 2)
        self.assertTrue(res["ready"])

    def test_all_downloads_fail(self):
        def opener(req, timeout):
            raise OSError("offline")

        with self.assertRaises(ollama_setup.InstallError) as ctx:
            ollama_setup.install(self.tmp / "home", "http://127.0.0.1:1", None, urls=("https://a.invalid/x.zip",),
                                 run=FakeRun(), opener=opener, apps_dir=self.apps, wait=lambda *a: True)
        self.assertIn("網路", str(ctx.exception))

    def test_stop_during_download(self):
        stop = threading.Event()
        stop.set()
        res = ollama_setup.install(self.tmp / "home", "http://127.0.0.1:1", None, stop=stop, urls=("https://a.invalid/x.zip",),
                                   run=FakeRun(), opener=lambda req, timeout: FakeResp(fake_zip()), apps_dir=self.apps, wait=lambda *a: True)
        self.assertTrue(res["stopped"])
        self.assertFalse((self.apps / "Ollama.app").exists())

    def test_target_dir(self):
        self.assertEqual(ollama_setup.target_dir(None), Path.home() / "Applications")
        self.apps.mkdir()
        self.assertEqual(ollama_setup.target_dir(str(self.apps / "Ollama.app")), self.apps)


class ModelTests(unittest.TestCase):
    def test_assistant_prefers_qwen_with_enough_memory(self):
        self.assertEqual(recommend_assistant(48), "qwen3.8:27b")
        self.assertEqual(recommend_assistant(36), "qwen3.8:27b")
        self.assertEqual(recommend_assistant(32), "gemma4:26b")
        self.assertEqual(recommend_assistant(16), "gemma4:e4b")

    def test_photo_analysis_keeps_the_faster_model(self):
        # 照片量大，速度優先：48 GB 仍然推薦 gemma4:26b 分析照片
        self.assertEqual(recommend(48)["best"], "gemma4:26b")

    def test_newer_ollama_message(self):
        msg = _pull_error("qwen3.8:27b", "pull model manifest: 412: The model you are attempting to pull requires a newer version of Ollama.")
        self.assertIn("更新 Ollama", msg)


class FakeVision:
    def __init__(self, fail_model=None):
        self.calls = []
        self.fail_model = fail_model

    def describe(self, model, prompt, images):
        self.calls.append(model)
        if model == self.fail_model:
            raise RuntimeError("模型壞了")
        return {"description": f"{model} 看到一張照片", "tags": ["照片", model], "text_in_image": "ABC" if "qwen" in model else ""}


class CompareTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        photos = self.tmp / "照片"
        photos.mkdir()
        for i in range(5):
            Image.new("RGB", (64, 48), (i * 40, 80, 120)).save(photos / f"p{i}.jpg")
        db.add_root(self.conn, photos, "照片")
        scan_all(self.conn, self.cfg)
        self.assertGreaterEqual(self.conn.execute("SELECT COUNT(*) FROM images WHERE media_type = 'photo'").fetchone()[0], 5)

    def test_runs_each_model_on_same_photos(self):
        client = FakeVision()
        before = self.conn.execute("SELECT COUNT(*) FROM images WHERE description IS NOT NULL AND description != ''").fetchone()[0]
        res = compare_models.run(self.conn, self.cfg, client, ["gemma4:26b", "qwen3.8:27b"], 4, seed=1)
        self.assertEqual(client.calls, ["gemma4:26b"] * 4 + ["qwen3.8:27b"] * 4)  # 一個模型跑完再換下一個
        self.assertEqual(len(res["items"]), 4)
        self.assertEqual([m["ok"] for m in res["models"]], [4, 4])
        self.assertEqual(res["models"][1]["text_found"], 4)
        self.assertEqual(compare_models.last(self.conn)["models"][0]["model"], "gemma4:26b")
        after = self.conn.execute("SELECT COUNT(*) FROM images WHERE description IS NOT NULL AND description != ''").fetchone()[0]
        self.assertEqual(before, after)  # 不寫進圖庫
        self.assertIn("比較完成", compare_models.describe(res))

    def test_records_errors_per_model(self):
        res = compare_models.run(self.conn, self.cfg, FakeVision(fail_model="bad"), ["gemma4:26b", "bad"], 3, seed=1)
        self.assertEqual(res["models"][1]["errors"], 3)
        self.assertIsNone(res["models"][1]["median_seconds"])
        self.assertIn("模型壞了", res["items"][0]["results"]["bad"]["error"])

    def test_needs_two_models(self):
        with self.assertRaises(ValueError):
            compare_models.run(self.conn, self.cfg, FakeVision(), ["gemma4:26b", "gemma4:26b"], 3)

    def test_skips_photos_that_cannot_be_read(self):
        shutil.rmtree(self.tmp / "照片")  # 硬碟拔掉了
        with self.assertRaises(ValueError):
            compare_models.run(self.conn, self.cfg, FakeVision(), ["a", "b"], 3)

    def test_stop(self):
        stop = threading.Event()
        client = FakeVision()

        def progress(done, total, name):
            if done == 2:
                stop.set()

        res = compare_models.run(self.conn, self.cfg, client, ["a", "b"], 4, stop=stop, progress=progress, seed=1)
        self.assertTrue(res["stopped"])
        self.assertEqual(len(client.calls), 2)


if __name__ == "__main__":
    unittest.main()
