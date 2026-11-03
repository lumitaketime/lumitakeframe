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
        FakeOllama.answer_in_thinking = False
        OllamaClient._no_think = set()
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
        self.cfg = load_config(self.tmp / "home", vision_model="qwen2.5vl:7b")
        conn = db.connect(self.cfg.db_path)
        db.add_root(conn, self.tmp / "photos")
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_scan(self, client_cls):
        runner = JobRunner(self.cfg, client_cls)
        try:
            runner.submit("scan")
            self.assertTrue(runner.wait_idle(30))
            return runner.last
        finally:
            runner.close()

    def test_scan_then_analyze_when_ready(self):
        last = self.run_scan(ReadyClient)
        self.assertEqual(last["kind"], "analyze")
        conn = db.connect(self.cfg.db_path)
        self.assertEqual(db.stats(conn)["analyzed"], 1)
        conn.close()

    def test_scan_explains_when_model_missing(self):
        class Missing(ReadyClient):
            def list_models(self):
                return ["other:1b"]

        last = self.run_scan(Missing)
        self.assertEqual(last["kind"], "scan")
        self.assertIn("尚未開始 AI 分析", last["message"])

    def test_pull_of_selected_model_starts_analysis(self):
        from lumilib.scanner import scan_all

        conn = db.connect(self.cfg.db_path)
        scan_all(conn, self.cfg)
        conn.close()
        runner = JobRunner(self.cfg, ReadyClient)
        try:
            runner.submit("pull", model="qwen2.5vl:7b")
            self.assertTrue(runner.wait_idle(30))
            self.assertEqual(runner.last["kind"], "analyze")
        finally:
            runner.close()

    def test_auto_analyze_off(self):
        self.cfg.auto_analyze = 0
        self.assertEqual(self.run_scan(ReadyClient)["kind"], "scan")


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
