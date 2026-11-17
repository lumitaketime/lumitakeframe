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
            events = list(assistant.ask(self.conn, client, "http://127.0.0.1:11434", "gemma4:e4b", question, [], "備份A", "zh-Hant"))
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
            events = list(assistant.ask(self.conn, FakeClient([]), "http://x", "m", "你好"))
        self.assertEqual(events[-1], {"type": "error", "message": "沒有連到 Ollama。"})

    def test_status_and_suggestions(self):
        self.assertTrue(assistant.status(FakeClient([]), "gemma4:e4b")["model_ready"])
        self.assertFalse(assistant.status(FakeClient([], models=()), "gemma4:e4b")["model_ready"])
        keys = [s["key"] for s in assistant.suggestions(self.conn)]
        self.assertIn("ask_find", keys)


if __name__ == "__main__":
    unittest.main()
