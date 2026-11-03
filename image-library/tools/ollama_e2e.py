"""用真的 Ollama 跑一次完整流程（CI 用）：下載照片 → 掃描 → AI 分析 → 搜尋改寫。

用法：python tools/ollama_e2e.py <模型名稱> <照片資料夾>
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lumilib import db  # noqa: E402
from lumilib.analyzer import OllamaClient, ai_status, analyze_images, rewrite_query  # noqa: E402
from lumilib.config import load_config  # noqa: E402
from lumilib.scanner import scan_all  # noqa: E402

model, photos = sys.argv[1], Path(sys.argv[2])
home = Path("/tmp/lumilib-e2e-" + model.replace(":", "_"))
cfg = load_config(home, vision_model=model)
client = OllamaClient(cfg.ollama_url, 900)

tags = json.load(urllib.request.urlopen(cfg.ollama_url + "/api/tags"))
for m in tags["models"]:
    print(f"已安裝 {m['name']}: {m['size'] / 1e9:.2f} GB, {m.get('details', {}).get('parameter_size')}")
status = ai_status(client, cfg)
print("ai_status", status)
assert status["ready"], status

conn = db.connect(cfg.db_path)
db.add_root(conn, photos)
scan_all(conn, cfg)
t0 = time.monotonic()
res = analyze_images(conn, cfg, client, progress=lambda i, n, m: print(f"  {i}/{n} {m} {time.monotonic() - t0:.0f}s", flush=True))
elapsed = time.monotonic() - t0
print(f"分析 {res.analyzed}、失敗 {res.failed}，共 {elapsed:.0f} 秒")
for e in res.errors:
    print("錯誤", e)
for row in conn.execute("SELECT rel_path, description, tags, scene, ocr_text FROM images ORDER BY rel_path"):
    print("─" * 60)
    print(row["rel_path"])
    print("描述：", row["description"])
    print("關鍵字：", row["tags"])
    print("場景：", row["scene"], "｜文字：", row["ocr_text"])

t1 = time.monotonic()
rw = rewrite_query(client, model, ["狗", "海邊"], timeout=300)
print(f"搜尋改寫（{time.monotonic() - t1:.0f} 秒）：", rw)

summary = {"model": model, "analyzed": res.analyzed, "failed": res.failed, "seconds": round(elapsed),
           "per_image": round(elapsed / max(1, res.analyzed + res.failed), 1)}
print("SUMMARY", json.dumps(summary, ensure_ascii=False))
assert res.analyzed >= max(1, (res.analyzed + res.failed) - 1), "大部分照片都分析失敗"
