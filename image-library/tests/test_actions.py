"""助理的權限與動作：提案不動硬碟；本人確認後才執行；執行前逐項驗證、不覆蓋；每一個動作都能復原。"""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from lumilib import actions, assistant, db
from lumilib import llm as llm_mod
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def snapshot(root):
    return sorted((str(p.relative_to(root)), p.stat().st_size) for p in root.rglob("*"))


class ActionTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "備份A"
        (d / "雜物").mkdir(parents=True)
        (d / "照片").mkdir()
        for name, body in (("a.txt", "一"), ("b.txt", "二二"), ("報告.docx", "三三三")):
            (d / "雜物" / name).write_text(body, encoding="utf-8")
        (d / "照片" / "a.txt").write_text("已經有同名的", encoding="utf-8")
        db.add_root(self.conn, d, "備份A")
        scan_all(self.conn, self.cfg)

    def fid(self, name, folder="雜物"):
        return self.conn.execute("SELECT f.id FROM files f JOIN folders d ON d.id = f.folder_id WHERE f.name = ? AND d.path = ?",
                                 (name, folder)).fetchone()[0]

    def where(self, file_id):
        r = self.conn.execute("SELECT d.path, f.name FROM files f JOIN folders d ON d.id = f.folder_id WHERE f.id = ?", (file_id,)).fetchone()
        return f"{r[0]}/{r[1]}" if r[0] else r[1]

    def total(self, path):
        return self.conn.execute("SELECT total_files FROM folders WHERE path = ?", (path,)).fetchone()[0]

    def test_permission_levels(self):
        self.assertNotIn("read_document", assistant.allowed_tools(assistant.Ctx(1)))
        self.assertIn("read_document", assistant.allowed_tools(assistant.Ctx(2)))
        self.assertNotIn("read_document", assistant.allowed_tools(assistant.Ctx(2, content=False)))  # 雲端：沒允許就不送內容
        self.assertNotIn("propose_label", assistant.allowed_tools(assistant.Ctx(2)))
        self.assertIn("propose_label", assistant.allowed_tools(assistant.Ctx(3)))
        self.assertNotIn("propose_move", assistant.allowed_tools(assistant.Ctx(3)))
        self.assertIn("propose_move", assistant.allowed_tools(assistant.Ctx(4)))
        with self.assertRaises(actions.ActionError):
            actions.propose(self.conn, "move", {"file_ids": [self.fid("a.txt")], "folder": "x"}, level=3)

    def test_move_runs_only_after_confirm_and_can_be_undone(self):
        before = snapshot(self.drive)
        ids = [self.fid("b.txt"), self.fid("報告.docx")]
        a = actions.propose(self.conn, "move", {"file_ids": ids, "folder": "整理好/2008"}, level=4)
        self.assertEqual(a["state"], "proposed")
        self.assertEqual(snapshot(self.drive), before)  # 提案不動硬碟
        self.assertEqual([i["to"] for i in a["items"]], ["整理好/2008/b.txt", "整理好/2008/報告.docx"])

        done = actions.run(self.conn, a["id"], level=4)
        self.assertEqual(done["state"], "done")
        self.assertTrue((self.drive / "整理好" / "2008" / "b.txt").is_file())
        self.assertFalse((self.drive / "雜物" / "b.txt").exists())
        self.assertEqual(self.where(ids[0]), "整理好/2008/b.txt")  # 目錄跟著更新
        self.assertEqual(self.total("整理好"), 2)
        self.assertEqual(self.total("雜物"), 1)
        with self.assertRaises(actions.ActionError):
            actions.run(self.conn, a["id"], level=4)  # 不能做兩次

        back = actions.undo(self.conn, a["id"])
        self.assertEqual(back["state"], "undone")
        self.assertEqual(snapshot(self.drive), before)  # 完全回到原樣（建立的空資料夾也拿掉了）
        self.assertEqual(self.where(ids[0]), "雜物/b.txt")
        self.assertEqual(self.total("雜物"), 3)
        self.assertIsNone(self.conn.execute("SELECT id FROM folders WHERE path = '整理好'").fetchone())

    def test_never_overwrites_and_skips_changed_files(self):
        a = actions.propose(self.conn, "move", {"file_ids": [self.fid("a.txt"), self.fid("b.txt")], "folder": "照片"}, level=4)
        (self.drive / "雜物" / "b.txt").write_text("掃描之後改過", encoding="utf-8")
        out = actions.run(self.conn, a["id"], level=4)
        self.assertEqual(out["state"], "failed")
        self.assertEqual([i["status"] for i in out["items"]], ["skipped", "skipped"])
        self.assertIn("同名", out["items"][0]["reason"])
        self.assertIn("改過", out["items"][1]["reason"])
        self.assertEqual((self.drive / "照片" / "a.txt").read_text(encoding="utf-8"), "已經有同名的")  # 沒被覆蓋
        self.assertTrue((self.drive / "雜物" / "a.txt").is_file())

    def test_only_checked_items_and_permission_at_run_time(self):
        a = actions.propose(self.conn, "to_pending", {"file_ids": [self.fid("a.txt"), self.fid("b.txt")]}, level=4)
        with self.assertRaises(actions.ActionError):
            actions.run(self.conn, a["id"], level=2)  # 提案之後權限調低了：不執行
        out = actions.run(self.conn, a["id"], level=4, only=[1])
        self.assertEqual(out["state"], "done")  # 勾選的都做好了；沒勾的記成「沒有勾選」
        self.assertEqual(out["items"][0]["reason"], "沒有勾選")
        self.assertTrue((self.drive / actions.PENDING_DIR / "雜物" / "b.txt").is_file())  # 保留原本的資料夾結構
        self.assertTrue((self.drive / "雜物" / "a.txt").is_file())

    def test_rename_keeps_extension(self):
        with self.assertRaises(actions.ActionError):
            actions.propose(self.conn, "rename", {"renames": [{"file_id": self.fid("報告.docx"), "new_name": "報告.pdf"}]}, level=4)
        with self.assertRaises(actions.ActionError):
            actions.propose(self.conn, "rename", {"renames": [{"file_id": self.fid("a.txt"), "new_name": "../a.txt"}]}, level=4)
        a = actions.propose(self.conn, "rename", {"renames": [{"file_id": self.fid("報告.docx"), "new_name": "2008 期末報告.docx"}]}, level=4)
        actions.run(self.conn, a["id"], level=4)
        self.assertTrue((self.drive / "雜物" / "2008 期末報告.docx").is_file())
        actions.undo(self.conn, a["id"])
        self.assertTrue((self.drive / "雜物" / "報告.docx").is_file())

    def test_catalog_only_actions(self):
        before = snapshot(self.drive)
        fid = self.fid("a.txt")
        a = actions.propose(self.conn, "label", {"file_ids": [fid], "color": "green"}, level=3)
        actions.run(self.conn, a["id"], level=3)
        self.assertEqual(self.conn.execute("SELECT label FROM files WHERE id = ?", (fid,)).fetchone()[0], "green")
        actions.undo(self.conn, a["id"])
        self.assertIsNone(self.conn.execute("SELECT label FROM files WHERE id = ?", (fid,)).fetchone()[0])

        s = actions.run(self.conn, actions.propose(self.conn, "smart_folder", {"name": "報告", "query": "報告"}, level=3)["id"], level=3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM smart_folders").fetchone()[0], 1)
        actions.undo(self.conn, s["id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM smart_folders").fetchone()[0], 0)

        # 待刪除標記：只能標記確認過內容一樣、而且還有別份保留的副本
        with self.assertRaises(actions.ActionError):
            actions.propose(self.conn, "mark_delete", {"file_ids": [fid]}, level=3)
        other = self.fid("a.txt", "照片")
        self.conn.execute("UPDATE files SET content_hash = 'h', size = 9 WHERE id IN (?, ?)", (fid, other))
        with self.assertRaises(actions.ActionError):
            actions.propose(self.conn, "mark_delete", {"file_ids": [fid, other]}, level=3)  # 兩份都標就沒有保留的了
        m = actions.propose(self.conn, "mark_delete", {"file_ids": [fid]}, level=3)
        actions.run(self.conn, m["id"], level=3)
        self.assertEqual(self.conn.execute("SELECT item_id FROM delete_marks").fetchall()[0][0], fid)
        actions.undo(self.conn, m["id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM delete_marks").fetchone()[0], 0)
        self.assertEqual(snapshot(self.drive), before)  # 這些只寫目錄

    def test_assistant_proposes_but_does_not_execute(self):
        before = snapshot(self.drive)
        fid = self.fid("a.txt")
        rounds = [[{"tool": "search_files", "args": {"query": "a"}}],
                  [{"tool": "propose_to_pending", "args": {"file_ids": [fid]}}], []]

        class Client:
            def chat_json(self, model, prompt, schema, **kw):
                return {"calls": rounds.pop(0) if rounds else []}

        def stream(base_url, payload, timeout=300):
            yield {"message": {"content": "請檢查提案。"}}

        with mock.patch.object(llm_mod, "_post_ollama", stream):
            events = list(assistant.ask(self.conn, assistant.OllamaLLM(Client(), "http://x", "m"), "把 a.txt 丟到待刪除", level=4))
        acts = [e for e in events if e["type"] == "action"]
        self.assertEqual(len(acts), 1)
        self.assertEqual(acts[0]["action"]["kind"], "to_pending")
        self.assertEqual(events[-1]["actions"], [acts[0]["action"]["id"]])
        self.assertEqual(snapshot(self.drive), before)

    def test_api_requires_confirmation(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        self.cfg.save_setting("assistant_permission", 4)
        a = actions.propose(self.conn, "move", {"file_ids": [self.fid("a.txt")], "folder": "新"}, level=4)
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            self.assertEqual(c.post("/api/assistant/actions/run", json={"id": a["id"]}).status_code, 400)
            self.assertTrue((self.drive / "雜物" / "a.txt").exists())
            r = c.post("/api/assistant/actions/run", json={"id": a["id"], "confirm": True}).json()
            self.assertEqual(r["state"], "done")
            self.assertEqual(c.get("/api/assistant/actions").json()[0]["id"], a["id"])
            self.assertEqual(c.post("/api/assistant/actions/undo", json={"id": a["id"], "confirm": True}).json()["state"], "undone")
            self.assertEqual(c.post("/api/settings", json={"assistant_permission": 9}).json()["assistant_permission"], 4)
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://192.168.1.5:8766", client=("192.168.1.9", 1)) as c:
            self.assertIn(c.post("/api/assistant/actions/run", json={"id": a["id"], "confirm": True}).status_code, (401, 403))


class ClaudeTests(unittest.TestCase):
    """Claude：用官方套件連到一個本機的假服務，確認串流、規劃、錯誤訊息與備援參數。"""

    def setUp(self):
        seen = self.seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((dict(self.headers), body))
                auth = (self.headers.get("x-api-key") or "") + (self.headers.get("Authorization") or "")
                if "sk-ant-test" not in auth:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"type":"error","error":{"type":"authentication_error","message":"bad key"}}')
                    return
                msg = {"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"], "content": [],
                       "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}
                if not body.get("stream"):
                    msg["content"] = [{"type": "text", "text": '{"calls": []}'}]
                    msg["stop_reason"] = "end_turn"
                    data = json.dumps(msg).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                events = [("message_start", {"type": "message_start", "message": msg}),
                          ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                          ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好"}}),
                          ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "！"}}),
                          ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                          ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                             "usage": {"output_tokens": 2}}),
                          ("message_stop", {"type": "message_stop"})]
                for name, data in events:
                    self.wfile.write(f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def claude(self, model="claude-opus-5-5", key="sk-ant-test"):
        import anthropic

        return llm_mod.ClaudeLLM(model, key, client=anthropic.Anthropic(api_key=key, base_url=self.url, max_retries=0))

    def test_stream_and_plan(self):
        c = self.claude()
        msgs = [{"role": "system", "content": "規則"}, {"role": "user", "content": "嗨"}]
        self.assertEqual("".join(c.stream(msgs)), "你好！")
        headers, body = self.seen[-1]
        self.assertEqual(body["system"], "規則")  # system 放在最上層，不在對話裡
        self.assertEqual([m["role"] for m in body["messages"]], ["user"])
        self.assertEqual(body["fallbacks"], "default")  # Opus：拒絕回答時由 Anthropic 改用其他模型
        self.assertIn(llm_mod.CLAUDE_FALLBACK_BETA, headers.get("anthropic-beta", ""))
        self.assertEqual(c.plan_json("規劃", {}), {"calls": []})
        self.assertEqual(self.seen[-1][1]["output_config"], {"effort": "low"})
        self.assertTrue(c.remote)

        h = self.claude("claude-haiku-5-5")
        "".join(h.stream(msgs))
        self.assertNotIn("fallbacks", self.seen[-1][1])

    def test_bad_key_is_explained(self):
        with self.assertRaises(RuntimeError) as cm:
            "".join(self.claude(key="wrong").stream([{"role": "user", "content": "嗨"}]))
        self.assertIn("金鑰", str(cm.exception))

    def test_provider_settings(self):
        class Cfg:
            assistant_provider = "claude"
            assistant_claude_model = ""
            assistant_claude_key = "k"
            assistant_openai_key = ""
            assistant_api_url = "http://127.0.0.1:1234/v1"
            assistant_model = ""
            ollama_url = "http://127.0.0.1:11434"

        cfg = Cfg()
        self.assertEqual(llm_mod.api_settings(cfg, "claude")["model"], "claude-opus-5-5")
        self.assertIsInstance(llm_mod.make_llm(cfg, None), llm_mod.ClaudeLLM)
        self.assertTrue(llm_mod.is_remote(cfg))
        cfg.assistant_provider = "openai"  # 舊版的「openai」其實是任何相容的網址
        self.assertEqual(llm_mod.provider_of(cfg), "custom")
        self.assertFalse(llm_mod.is_remote(cfg))
        cfg.assistant_provider = "gemini"
        self.assertIn("generativelanguage.googleapis.com", llm_mod.make_llm(cfg, None).base_url)


class HardwareTests(unittest.TestCase):
    def test_assistant_model_follows_memory(self):
        from lumilib.models import recommend_assistant

        self.assertEqual(recommend_assistant(8), "gemma4:e2b")
        self.assertEqual(recommend_assistant(16), "gemma4:e4b")
        self.assertEqual(recommend_assistant(32), "gemma4:26b")
        self.assertEqual(recommend_assistant(36), "qwen3.8:27b")
        self.assertEqual(recommend_assistant(64), "qwen3.8:27b")
        self.assertEqual(recommend_assistant(4), "gemma4:e2b")


if __name__ == "__main__":
    unittest.main()
