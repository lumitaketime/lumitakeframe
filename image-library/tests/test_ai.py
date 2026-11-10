"""AI 分析流程：關閉思考模式、準備狀態、掃描後自動分析、依電腦推薦模型、HTTPS 憑證。"""

import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lumilib import db
from lumilib.analyzer import OllamaClient, ai_status
from lumilib.config import load_config
from lumilib.jobs import JobRunner
from lumilib.models import RECOMMENDED, annotated, recommend

from test_library import FakeClient, make_photo


class FakeOllama(BaseHTTPRequestHandler):
    """模擬 Ollama：可設定成不支援 think 參數，或把答案放在 thinking。"""

    reject_think = False
    reject_format = False
    answer_in_thinking = False
    requests: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"models": [{"name": "gemma4:e4b", "size": 1, "details": {}}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(payload)
        if "format" in payload and self.reject_format:
            self.send_response(501)
            self.end_headers()
            self.wfile.write(b'{"error":"structured output is unavailable"}')
            return
        if "think" in payload and self.reject_think:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"\\"m\\" does not support thinking"}')
            return
        answer = json.dumps({"description": "海邊", "tags": ["beach"], "objects": [], "scene": "海邊",
                             "text_in_image": ""})
        msg = {"role": "assistant", "content": "", "thinking": answer} if self.answer_in_thinking else \
            {"role": "assistant", "content": answer}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"message": msg}).encode())


class OllamaClientTests(unittest.TestCase):
    def setUp(self):
        FakeOllama.requests = []
        FakeOllama.reject_think = False
        FakeOllama.reject_format = False
        FakeOllama.answer_in_thinking = False
        OllamaClient._no_think = set()
        OllamaClient._no_format = set()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.client = OllamaClient(f"http://127.0.0.1:{self.server.server_address[1]}", 10)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_disables_thinking_and_sets_context(self):
        out = self.client.describe("gemma4:e4b", "describe", ["aGk="])
        self.assertEqual(out["tags"], ["beach"])
        req = FakeOllama.requests[0]
        self.assertIs(req["think"], False)
        self.assertGreaterEqual(req["options"]["num_ctx"], 8192)
        self.assertIn("format", req)

    def test_retries_without_think_when_unsupported(self):
        FakeOllama.reject_think = True
        out = self.client.describe("old-model", "describe", ["aGk="])
        self.assertEqual(out["description"], "海邊")
        self.assertNotIn("think", FakeOllama.requests[-1])
        # 之後同一個模型不再送 think
        self.client.describe("old-model", "describe", ["aGk="])
        self.assertEqual(len(FakeOllama.requests), 3)

    def test_falls_back_when_structured_output_unavailable(self):
        FakeOllama.reject_format = True
        out = self.client.describe("gemma4:e4b", "describe", ["aGk="])
        self.assertEqual(out["scene"], "海邊")
        last = FakeOllama.requests[-1]
        self.assertNotIn("format", last)
        self.assertIn("JSON", last["messages"][-1]["content"])
        self.assertIn("gemma4:e4b", OllamaClient._no_format)

    def test_answer_in_thinking_field(self):
        FakeOllama.answer_in_thinking = True
        self.assertEqual(self.client.describe("m", "p", ["aGk="])["scene"], "海邊")

    def test_ai_status(self):
        cfg = load_config(tempfile.mkdtemp(), vision_model="gemma4:e4b")
        self.assertTrue(ai_status(self.client, cfg)["ready"])
        cfg.vision_model = "qwen3-vl:8b"
        st = ai_status(self.client, cfg)
        self.assertFalse(st["ready"])
        self.assertTrue(st["ollama"])
        self.assertIn("還沒下載", st["message"])
        st = ai_status(OllamaClient("http://127.0.0.1:9", 2), cfg)
        self.assertFalse(st["ollama"])
        self.assertTrue("Ollama" in st["message"])


class ReadyClient(FakeClient):
    def list_models(self):
        return [m["name"] for m in self.installed()]


class AutoAnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        make_photo(self.tmp / "photos" / "a.jpg", (230, 30, 30))
        # 預設不自動分析；這組測試檢查「開啟自動分析」時的行為
        self.cfg = load_config(self.tmp / "home", vision_model="qwen2.5vl:7b", auto_analyze=1)
        conn = db.connect(self.cfg.db_path)
        db.add_root(conn, self.tmp / "photos")
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_does_not_auto_analyze(self):
        self.assertEqual(load_config(self.tmp / "other").auto_analyze, 0)
        self.cfg.auto_analyze = 0
        done = self.run_scan(ReadyClient)
        self.assertNotIn("analyze", done)
        conn = db.connect(self.cfg.db_path)
        self.assertEqual(db.stats(conn)["analyzed"], 0)
        conn.close()

    def run_scan(self, client_cls):
        runner = JobRunner(self.cfg, client_cls)
        try:
            runner.submit("scan")
            self.assertTrue(runner.wait_idle(30))
            return {j["kind"]: j for j in reversed(runner.recent)}  # 每種工作最後一次的結果
        finally:
            runner.close()

    def test_scan_then_analyze_when_ready(self):
        done = self.run_scan(ReadyClient)
        self.assertIn("analyze", done)
        self.assertNotIn("quality", done)  # 品質檢查已移除
        conn = db.connect(self.cfg.db_path)
        self.assertEqual(db.stats(conn)["analyzed"], 1)
        conn.close()

    def test_scan_explains_when_model_missing(self):
        class Missing(ReadyClient):
            def list_models(self):
                return ["other:1b"]

        done = self.run_scan(Missing)
        self.assertNotIn("analyze", done)
        self.assertIn("尚未開始 AI 分析", done["scan"]["message"])

    def test_pull_of_selected_model_starts_analysis(self):
        from lumilib.scanner import scan_all

        conn = db.connect(self.cfg.db_path)
        scan_all(conn, self.cfg)
        conn.close()
        runner = JobRunner(self.cfg, ReadyClient)
        try:
            runner.submit("pull", model="qwen2.5vl:7b")
            self.assertTrue(runner.wait_idle(30))
            self.assertIn("analyze", [j["kind"] for j in runner.recent])
        finally:
            runner.close()

    def test_auto_analyze_off(self):
        self.cfg.auto_analyze = 0
        self.assertNotIn("analyze", self.run_scan(ReadyClient))


class BrokenServerClient(ReadyClient):
    def describe(self, model, prompt, images):
        raise RuntimeError('Ollama 回應 500：{"error":"boom"}')


class StopOnRepeatedErrorsTests(unittest.TestCase):
    def test_stops_and_keeps_photos_pending(self):
        from lumilib.analyzer import OllamaUnavailable, analyze_images, reset_server_errors
        from lumilib.scanner import scan_all

        tmp = Path(tempfile.mkdtemp())
        try:
            for i in range(5):
                make_photo(tmp / "p" / f"{i}.jpg", (20 * i, 30, 30))
            cfg = load_config(tmp / "home")
            conn = db.connect(cfg.db_path)
            db.add_root(conn, tmp / "p")
            scan_all(conn, cfg)
            with self.assertRaises(OllamaUnavailable):
                analyze_images(conn, cfg, BrokenServerClient())
            st = db.stats(conn)
            self.assertEqual(st["failed"], 0)  # 伺服器的問題不算照片失敗
            self.assertEqual(st["pending"], 5)
            conn.execute("UPDATE images SET error = 'Ollama 回應 501：x' WHERE id = 1")
            self.assertEqual(reset_server_errors(conn), 1)
            self.assertEqual(db.stats(conn)["pending"], 5)
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RecommendTests(unittest.TestCase):
    def test_picks_fit_memory(self):
        by_name = {m["name"]: m for m in RECOMMENDED}
        for ram in (8, 16, 32, 64):
            picks = recommend(ram)
            for key in ("best", "fast"):
                self.assertLessEqual(by_name[picks[key]]["min_ram"], ram, (ram, picks))
        self.assertIn(recommend(64)["best"], {"gemma4:31b", "gemma4:26b", "qwen3-vl:30b"})
        self.assertTrue(any(m["name"].startswith("gemma4") for m in RECOMMENDED))

    def test_annotated(self):
        rows = {m["name"]: m for m in annotated(16, ["gemma4:e4b"])}
        self.assertTrue(rows["gemma4:e4b"]["installed"])
        self.assertEqual(rows["gemma4:31b"]["fit"], "too_big")
        self.assertEqual(sum(1 for r in rows.values() if r["badge"] == "最適合這台電腦"), 1)


class CertificateTests(unittest.TestCase):
    def test_context_has_certificates_without_system_store(self):
        from lumilib import net

        old = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = "/nonexistent/cert.pem"
        net._context = None
        try:
            ctx = net.ssl_context()
            self.assertGreater(ctx.cert_store_stats()["x509_ca"], 50)
        finally:
            net._context = None
            if old is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = old

    def test_friendly_certificate_error(self):
        from lumilib.net import describe_error

        self.assertIn("憑證", describe_error(Exception("[SSL: CERTIFICATE_VERIFY_FAILED] x")))


if __name__ == "__main__":
    unittest.main()


class LaneTests(unittest.TestCase):
    def test_scan_and_downloads_do_not_wait_for_analysis(self):
        import time

        from lumilib.scanner import scan_all

        tmp = Path(tempfile.mkdtemp())
        release = threading.Event()

        class SlowClient(ReadyClient):
            def describe(self, model, prompt, images):
                release.wait(10)
                return super().describe(model, prompt, images)

            def pull(self, model, progress=None, stop=None):
                time.sleep(0.2)

        try:
            make_photo(tmp / "p" / "a.jpg", (230, 30, 30))
            cfg = load_config(tmp / "home", vision_model="qwen2.5vl:7b", auto_analyze=0)
            conn = db.connect(cfg.db_path)
            db.add_root(conn, tmp / "p")
            scan_all(conn, cfg)
            conn.close()
            runner = JobRunner(cfg, SlowClient)
            try:
                runner.submit("analyze")
                time.sleep(0.2)
                runner.submit("scan")
                runner.submit("pull", model="a:1b")
                runner.submit("pull", model="b:1b")
                snap = runner.snapshot()
                self.assertEqual(len([j for j in snap["active"] if j["lane"] == "download"]), 2)  # 同時下載
                end = time.monotonic() + 10
                while time.monotonic() < end and any(j["kind"] != "analyze" for j in runner.snapshot()["active"] + runner.snapshot()["queued"]):
                    time.sleep(0.05)
                kinds = [j["kind"] for j in runner.recent]
                self.assertIn("scan", kinds)  # 分析還在跑，掃描已經做完
                self.assertEqual(kinds.count("pull"), 2)
                self.assertEqual([j["kind"] for j in runner.snapshot()["active"]], ["analyze"])
                job_id = runner.snapshot()["active"][0]["id"]
                runner.stop(job_id)
                release.set()
                self.assertTrue(runner.wait_idle(10))
            finally:
                release.set()
                runner.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ScheduleTests(unittest.TestCase):
    def test_night_window_and_power(self):
        from datetime import datetime

        from lumilib import schedule

        cfg = load_config(tempfile.mkdtemp())
        self.assertTrue(schedule.analysis_allowed(cfg)[0])
        cfg.analyze_schedule = "night"
        self.assertTrue(schedule.analysis_allowed(cfg, datetime(2026, 1, 1, 23))[0])
        self.assertTrue(schedule.analysis_allowed(cfg, datetime(2026, 1, 1, 6))[0])
        ok, reason = schedule.analysis_allowed(cfg, datetime(2026, 1, 1, 12))
        self.assertFalse(ok)
        self.assertIn("22:00–07:00", reason)  # 舊版「只在夜間」轉成新排程
        cfg.analyze_schedule = "ac"
        from unittest import mock

        with mock.patch.object(schedule, "on_ac_power", return_value=False):
            self.assertFalse(schedule.analysis_allowed(cfg)[0])


class DetailTests(unittest.TestCase):
    def test_fast_prompt(self):
        from lumilib.analyzer import build_prompt

        cfg = load_config(tempfile.mkdtemp())
        image = {"taken_at": None, "media_type": "photo", "rel_path": "a/b.jpg"}
        standard = build_prompt(cfg, image)
        cfg.analysis_detail = "fast"
        fast = build_prompt(cfg, image)
        self.assertIn("8 到 12", fast)
        self.assertIn("10 到 25", standard)


class SalvageTests(unittest.TestCase):
    def test_truncated_json_keeps_complete_fields(self):
        from lumilib.analyzer import salvage_json

        text = '{"description": "雜誌內頁，日文排版。", "tags": ["雜誌", "書籍", "日語", "文'
        out = salvage_json(text)
        self.assertEqual(out["description"], "雜誌內頁，日文排版。")
        self.assertEqual(out["tags"], ["雜誌", "書籍", "日語"])
        self.assertIsNone(salvage_json("<think>still thinking"))
