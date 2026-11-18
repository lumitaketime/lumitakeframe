"""檔案管理助理：先選查詢工具、查目錄（唯讀）、再根據查到的資料回答並附上來源。用假的模型測試流程。"""

import shutil
import unittest
from pathlib import Path
from unittest import mock

from lumilib import assistant, db, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase

FIXTURES = Path(__file__).parent / "fixtures" / "docs"


class FakeClient:
    def __init__(self, calls, models=("gemma4:e4b",)):
        self.calls = calls
        self.models = list(models)
        self.prompts = []

    def chat_json(self, model, prompt, schema, timeout=None, num_predict=800, salvage=None):
        self.prompts.append(prompt)
        return {"calls": self.calls}

    def list_models(self):
        return self.models


class Cfg:
    assistant_provider = "ollama"
    assistant_model = "gemma4:e4b"
    ollama_url = "http://127.0.0.1:11434"
    assistant_api_url = ""
    assistant_api_model = ""
    assistant_api_key = ""


class AssistantTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "備份A"
        (d / "2008 國中").mkdir(parents=True)
        shutil.copy(FIXTURES / "report.pdf", d / "2008 國中" / "期末.pdf")  # 內容有「寄居蟹」
        db.add_root(self.conn, d, "備份A")
        scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)

    def run_ask(self, client, question, answer=("找到了，", "在 [1]。")):
        sent = []

        def fake_stream(base_url, payload, timeout=300):
            sent.append(payload)
            for piece in answer:
                yield {"message": {"content": piece}}
            yield {"done": True}

        with mock.patch.object(assistant, "_post_stream", fake_stream):
            llm = assistant.OllamaLLM(client, "http://127.0.0.1:11434", "gemma4:e4b")
            events = list(assistant.ask(self.conn, llm, question, [], "備份A", "zh-Hant"))
        return events, sent

    def test_looks_up_the_catalog_then_answers_with_sources(self):
        before = {p: p.stat().st_mtime for p in self.drive.rglob("*")}
        client = FakeClient([{"tool": "search_files", "args": {"query": "寄居蟹"}}])
        events, sent = self.run_ask(client, "我寫寄居蟹的報告在哪？")
        self.assertEqual(events[0], {"type": "step", "tool": "search_files", "args": {"query": "寄居蟹"}})
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "token"), "找到了，在 [1]。")
        done = events[-1]
        self.assertEqual(done["type"], "done")
        self.assertEqual(done["sources"][0]["name"], "期末.pdf")
        # 模型拿到的是查到的資料（含文件內容的片段），而且被要求不能刪除或搬移檔案
        user = sent[0]["messages"][-1]["content"]
        self.assertIn("期末.pdf", user)
        self.assertIn("寄居蟹", user)
        self.assertIn("不能刪除、搬移", sent[0]["messages"][0]["content"])
        self.assertEqual({p: p.stat().st_mtime for p in self.drive.rglob("*")}, before)  # 硬碟沒有被動到

    def test_every_tool_runs_read_only(self):
        fid = self.conn.execute("SELECT id FROM files WHERE name = '期末.pdf'").fetchone()[0]
        sources = []
        for name, args in [("largest_folders", {"limit": 5}), ("drives_overview", {}), ("duplicates", {}), ("read_document", {"file_id": fid}),
                           ("search_files", {"query": ""})]:
            out = assistant.RUN[name](self.conn, args, sources)
            self.assertIsInstance(out, str)
        self.assertIn("寄居蟹", assistant.RUN["read_document"](self.conn, {"file_id": fid}, sources))

    def test_unknown_tools_are_ignored_and_errors_reported(self):
        client = FakeClient([{"tool": "delete_everything", "args": {}}])
        events, _ = self.run_ask(client, "你好")
        self.assertFalse(any(e["type"] == "step" for e in events))  # 只能用唯讀的查詢工具

        def broken(base_url, payload, timeout=300):
            raise assistant.OllamaUnavailable("沒有連到 Ollama。")
            yield  # noqa: unreachable

        with mock.patch.object(assistant, "_post_stream", broken):
            events = list(assistant.ask(self.conn, assistant.OllamaLLM(FakeClient([]), "http://x", "m"), "你好"))
        self.assertEqual(events[-1], {"type": "error", "message": "沒有連到 Ollama。"})

    def test_status_and_suggestions(self):
        self.assertTrue(assistant.status(Cfg(), FakeClient([]))["model_ready"])
        self.assertFalse(assistant.status(Cfg(), FakeClient([], models=()))["model_ready"])
        api = Cfg()
        api.assistant_provider, api.assistant_api_url, api.assistant_api_model = "openai", "https://api.example.com/v1", "m"
        st = assistant.status(api, FakeClient([]))
        self.assertTrue(st["remote"])  # 雲端服務：介面要提醒資料會送出去
        api.assistant_api_url = "http://127.0.0.1:1234/v1"
        self.assertFalse(assistant.status(api, FakeClient([]))["remote"])  # 本機的 LM Studio 不算送出去
        keys = [s["key"] for s in assistant.suggestions(self.conn)]
        self.assertIn("ask_find", keys)


class OpenAICompatibleTests(CatalogTestCase):
    """OpenAI 相容的 API（例如 LM Studio）：用一個本機的假服務測試規劃、串流回答與金鑰。"""

    def test_plan_and_stream_over_the_api(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((self.headers.get("Authorization"), body))
                self.send_response(200)
                self.end_headers()
                if body.get("stream"):
                    for piece in ("你好", "！"):
                        self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n\n".encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                else:
                    content = json.dumps({"calls": []})
                    self.wfile.write(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            llm = assistant.OpenAILLM(f"http://127.0.0.1:{srv.server_port}/v1", "local-model", "sk-test")
            self.assertFalse(llm.remote)
            events = list(assistant.ask(self.conn, llm, "你好"))
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "token"), "你好！")
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(seen[0][0], "Bearer sk-test")
        self.assertEqual(seen[-1][1]["model"], "local-model")

    def test_api_key_is_never_sent_back(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            out = c.post("/api/settings", json={"assistant_provider": "openai", "assistant_api_key": "sk-secret"}).json()
            self.assertNotIn("assistant_api_key", out)
            self.assertTrue(out["assistant_api_key_set"])
            self.assertNotIn("sk-secret", c.get("/api/settings").text)
            c.post("/api/settings", json={"assistant_api_key": ""})  # 空白＝不改
            self.assertTrue(c.get("/api/settings").json()["assistant_api_key_set"])
            c.post("/api/settings", json={"assistant_api_key": "", "clear_api_key": True})
            self.assertFalse(c.get("/api/settings").json()["assistant_api_key_set"])


if __name__ == "__main__":
    unittest.main()
