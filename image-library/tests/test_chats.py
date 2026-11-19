"""助理的對話紀錄：問答（含查詢步驟、來源、提出的動作）存在這台電腦，換頁後打開得到；可以多選刪除。"""

import json
from unittest import mock

from lumilib import db, textindex
from lumilib import llm as llm_mod
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class Client:
    def chat_json(self, model, prompt, schema, **kw):
        return {"calls": [] if "已經查到的資料" in prompt else [{"tool": "search_files", "args": {"query": "預算"}}]}

    def list_models(self):
        return ["gemma4:e4b"]


def stream(base_url, payload, timeout=300):
    for piece in ("找到 ", "[1]。"):
        yield {"message": {"content": piece}}


class ChatTests(CatalogTestCase):
    def test_history_round_trip_and_delete(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        d = self.tmp / "碟"
        d.mkdir()
        (d / "預算表.txt").write_text("明年預算", encoding="utf-8")
        db.add_root(self.conn, d, "碟")
        scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)
        self.cfg.save_setting("assistant_model", "gemma4:e4b")
        app = create_app(self.cfg, start_jobs_on_boot=False, client_factory=lambda: Client())
        with mock.patch.object(llm_mod, "_post_ollama", stream), \
                TestClient(app, base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            def ask(q, chat_id=None):
                body = {"question": q, **({"chat_id": chat_id} if chat_id else {})}
                return [json.loads(x) for x in c.post("/api/assistant/ask", json=body).text.splitlines() if x]

            ev = ask("預算表在哪？")
            chat_id = ev[0]["id"]
            self.assertEqual(ev[0]["type"], "chat")
            ask("還有別的嗎？", chat_id)  # 同一段對話接著問
            second = ask("另一個問題")[0]["id"]
            self.assertNotEqual(second, chat_id)

            chats = c.get("/api/assistant/chats").json()
            self.assertEqual([x["id"] for x in chats], [second, chat_id])  # 最近的在前
            self.assertEqual(chats[1]["title"], "預算表在哪？")
            data = c.get(f"/api/assistant/chats/{chat_id}").json()
            self.assertEqual([m["role"] for m in data["messages"]], ["user", "assistant", "user", "assistant"])
            answer = data["messages"][1]
            self.assertEqual(answer["content"], "找到 [1]。")
            self.assertEqual(answer["sources"][0]["name"], "預算表.txt")  # 找到的資料也留著
            self.assertEqual(answer["steps"][0]["tool"], "search_files")

            self.assertEqual(c.post("/api/assistant/chats/delete", json={"ids": [chat_id, second]}).json()["deleted"], 2)
            self.assertEqual(c.get("/api/assistant/chats").json(), [])
            self.assertEqual(c.get(f"/api/assistant/chats/{chat_id}").status_code, 404)
        self.assertTrue((d / "預算表.txt").exists())  # 刪除紀錄不動檔案
