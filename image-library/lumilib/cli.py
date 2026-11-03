"""命令列介面：lumilib <指令>。執行 `lumilib -h` 查看全部指令。"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from . import __version__, db
from .analyzer import OllamaClient, OllamaUnavailable, analyze_images, embed_images
from .config import CONFIG_KEYS, load_config
from .media import HEIF_SUPPORT, tool_status
from .scanner import scan_all
from .search import search


def _print_scan(results) -> None:
    if not results:
        print("尚未加入任何資料夾，請先執行：lumilib add <資料夾路徑>")
    for r in results:
        if r.offline:
            print(f"[{r.root}] 目前無法存取（外接硬碟未連接？），已略過，紀錄保持不變")
            continue
        print(
            f"[{r.root}] 新增 {r.added}、內容更新 {r.updated}、搬移/改名 {r.moved}、"
            f"沿用重複檔分析 {r.reused}、未變更 {r.unchanged}、遺失 {r.missing}"
        )
        for err in r.errors[:10]:
            print(f"   ! {err}")


def _progress_printer():
    last = [0.0]

    def show(i: int, n: int, msg: str) -> None:
        now = time.monotonic()
        if now - last[0] > 0.5 or i == n:
            last[0] = now
            print(f"\r[{i}/{n}] {msg[:70]:<70}", end="", flush=True)
            if i == n:
                print()

    return show


def _run_analyze(conn, cfg, args) -> int:
    client = OllamaClient(cfg.ollama_url, cfg.request_timeout)
    stop = threading.Event()
    try:
        res = analyze_images(
            conn, cfg, client,
            limit=getattr(args, "limit", None),
            redo=getattr(args, "redo", False),
            retry_failed=getattr(args, "retry_failed", False),
            progress=_progress_printer(),
            stop=stop,
        )
    except OllamaUnavailable as exc:
        print(f"\n錯誤：{exc}")
        return 2
    except KeyboardInterrupt:
        stop.set()
        print("\n已中斷，已完成的分析都已保存，下次執行會從未完成的圖片繼續。")
        return 130
    print(f"分析完成 {res.analyzed} 張、失敗 {res.failed} 張、檔案無法存取 {res.skipped_offline} 張")
    if cfg.embed_model:
        print(f"建立語意向量 {res.embedded} 張")
    for err in res.errors[:10]:
        print(f"   ! {err}")
    return 0


def cmd_add(conn, cfg, args):
    root = db.add_root(conn, args.path, args.name)
    print(f"已加入「{root['name']}」：{root['path']}")
    if not args.no_scan:
        _print_scan(scan_all(conn, cfg, [root["name"]], progress=print))
        print("下一步：lumilib analyze（用地端模型分析圖片）")
    return 0


def cmd_roots(conn, cfg, args):
    roots = db.list_roots(conn)
    if not roots:
        print("尚未加入任何資料夾")
    for r in roots:
        from pathlib import Path

        online = "可存取" if Path(r["path"]).is_dir() else "未連接"
        print(f"{r['id']:>3}  {r['name']:<20} {r['image_count']:>7} 張  [{online}]  {r['path']}")
    return 0


def cmd_relocate(conn, cfg, args):
    root = db.relocate_root(conn, args.name, args.path)
    print(f"「{root['name']}」已改到：{root['path']}，接著執行掃描確認檔案…")
    _print_scan(scan_all(conn, cfg, [root["name"]]))
    return 0


def cmd_remove(conn, cfg, args):
    count = db.remove_root(conn, args.name)
    print(f"已從圖庫移除「{args.name}」與 {count} 筆圖片紀錄（硬碟上的檔案不受影響）")
    return 0


def cmd_scan(conn, cfg, args):
    _print_scan(scan_all(conn, cfg, args.roots or None, progress=print))
    return 0


def cmd_analyze(conn, cfg, args):
    return _run_analyze(conn, cfg, args)


def cmd_index(conn, cfg, args):
    _print_scan(scan_all(conn, cfg, progress=print))
    return _run_analyze(conn, cfg, args)


def cmd_embed(conn, cfg, args):
    if not cfg.embed_model:
        print("尚未設定向量模型，例如：lumilib config set embed_model bge-m3")
        return 1
    try:
        n = embed_images(conn, cfg, OllamaClient(cfg.ollama_url, cfg.request_timeout))
    except OllamaUnavailable as exc:
        print(f"錯誤：{exc}")
        return 2
    print(f"建立語意向量 {n} 張")
    return 0


def cmd_search(conn, cfg, args):
    q = " ".join(args.query)
    embedder = OllamaClient(cfg.ollama_url, 60) if args.semantic else None
    try:
        res = search(
            conn, q, limit=args.limit, semantic=args.semantic,
            embedder=embedder, embed_model=cfg.embed_model,
        )
    except OllamaUnavailable as exc:
        print(f"語意搜尋無法使用（{exc}），改用關鍵字搜尋")
        res = search(conn, q, limit=args.limit)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.paths:
        for r in res["results"]:
            print(r["path"])
        return 0
    print(f"找到 {res['total']} 張（顯示 {len(res['results'])} 張）")
    for r in res["results"]:
        date = (r["taken_at"] or "")[:10]
        tags = "、".join((r["user_tags"] + r["tags"])[:8])
        mark = "≈" if r["match"] == "semantic" else " "
        print(f"{mark}#{r['id']:<6} {date:<10} {r['path']}")
        if r["description"]:
            print(f"         {r['description'][:90]}")
        if tags:
            print(f"         [{tags}]")
    return 0


def cmd_tag(conn, cfg, args):
    image = db.get_image(conn, args.id)
    if image is None:
        print(f"找不到圖片 #{args.id}")
        return 1
    tags = db.json_list(image["user_tags"])
    tags += [t for t in args.add or [] if t not in tags]
    tags = [t for t in tags if t not in set(args.remove or [])]
    db.set_user_fields(conn, args.id, user_tags=tags, note=args.note)
    print(f"#{args.id} 手動標籤：{'、'.join(tags) or '（無）'}")
    return 0


def cmd_stats(conn, cfg, args):
    s = db.stats(conn)
    print(
        f"資料夾 {s['roots']} 個｜圖片 {s['images']} 張｜已分析 {s['analyzed']}｜"
        f"待分析 {s['pending']}｜失敗 {s['failed']}｜遺失 {s['missing']}｜語意向量 {s['embedded']}"
    )
    return 0


def cmd_doctor(conn, cfg, args):
    print(f"lumilib {__version__}，Python {sys.version.split()[0]}")
    print(f"資料目錄：{cfg.home}")
    print(f"HEIC 支援：{'有' if HEIF_SUPPORT else '無（pip install pillow-heif）'}")
    tools = tool_status()
    print(f"exiftool：{'有' if tools['exiftool'] else '無（brew install exiftool，RAW 與完整 EXIF 需要）'}")
    print(f"ffmpeg：{'有' if tools['ffmpeg'] else '無（brew install ffmpeg，影片需要）'}")
    try:
        import numpy  # noqa: F401

        print("numpy：有（語意搜尋較快）")
    except ImportError:
        print("numpy：無（語意搜尋可用但大型圖庫較慢，pip install numpy）")
    client = OllamaClient(cfg.ollama_url, 10)
    try:
        models = client.list_models()
    except OllamaUnavailable as exc:
        print(f"Ollama：無法連線 — {exc}")
        print("  安裝：https://ollama.com/download，安裝後執行：ollama pull " + cfg.vision_model)
        return 2
    print(f"Ollama：已連線 {cfg.ollama_url}，已下載 {len(models)} 個模型")

    def has(name: str) -> bool:
        return any(m == name or m == f"{name}:latest" or m.split(":")[0] == name for m in models)

    for label, name in (("視覺模型", cfg.vision_model), ("向量模型", cfg.embed_model)):
        if not name:
            print(f"{label}：未設定（選用）")
        elif has(name):
            print(f"{label}：{name} ✓")
        else:
            print(f"{label}：{name} 尚未下載 → ollama pull {name}")
    return 0


def cmd_config(conn, cfg, args):
    if args.action == "set":
        if args.key not in CONFIG_KEYS:
            print(f"未知設定：{args.key}，可用：{', '.join(CONFIG_KEYS)}")
            return 1
        cfg.save_setting(args.key, args.value)
        print(f"已設定 {args.key} = {getattr(cfg, args.key)}")
        return 0
    for key, value in cfg.as_dict().items():
        print(f"{key:<18} {value}")
    return 0


def cmd_password(conn, cfg, args):
    import getpass

    from .auth import Auth

    pw = getpass.getpass("新密碼（至少 6 個字元）：")
    if pw != getpass.getpass("再輸入一次：") :
        print("兩次輸入不一致")
        return 1
    Auth(cfg.auth_file).set_password(pw)
    print("已設定密碼。可在設定頁開啟「手機連線」。")
    return 0


def cmd_serve(conn, cfg, args):
    from .server import serve

    conn.close()
    serve(cfg, host=args.host, port=args.port, open_browser=args.open)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumilib",
        description="用地端模型分析圖片，之後以關鍵字從硬碟／SSD 找回照片。",
    )
    p.add_argument("--version", action="version", version=f"lumilib {__version__}")
    p.add_argument("--home", help="資料目錄（預設 ~/.lumilib，可用 LUMILIB_HOME 設定）")
    p.add_argument("--model", dest="vision_model", help="這次使用的視覺模型")
    p.add_argument("--ollama", dest="ollama_url", help="Ollama 位址，預設 http://127.0.0.1:11434")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("add", help="加入要管理的資料夾（例如整顆 SSD 或照片資料夾）並掃描")
    s.add_argument("path")
    s.add_argument("--name", help="顯示名稱，預設為資料夾名稱")
    s.add_argument("--no-scan", action="store_true", help="只登錄，不立即掃描")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("roots", help="列出已加入的資料夾")
    s.set_defaults(func=cmd_roots)

    s = sub.add_parser("relocate", help="硬碟換了代號或掛載位置時，更新資料夾路徑")
    s.add_argument("name")
    s.add_argument("path")
    s.set_defaults(func=cmd_relocate)

    s = sub.add_parser("remove", help="從圖庫移除資料夾（不會刪除硬碟上的檔案）")
    s.add_argument("name")
    s.set_defaults(func=cmd_remove)

    s = sub.add_parser("scan", help="重新掃描資料夾，找出新增、修改、搬移與遺失的檔案")
    s.add_argument("roots", nargs="*")
    s.set_defaults(func=cmd_scan)

    for name, func, help_text in (
        ("analyze", cmd_analyze, "用地端視覺模型分析尚未分析的圖片"),
        ("index", cmd_index, "掃描全部資料夾後分析（= scan + analyze）"),
    ):
        s = sub.add_parser(name, help=help_text)
        s.add_argument("--limit", type=int, help="最多分析幾張")
        s.add_argument("--redo", action="store_true", help="已分析過的也重新分析（例如換了模型）")
        s.add_argument("--retry-failed", action="store_true", help="重試先前失敗的圖片")
        s.set_defaults(func=func)

    s = sub.add_parser("embed", help="為已分析的圖片建立語意向量（需設定 embed_model）")
    s.set_defaults(func=cmd_embed)

    s = sub.add_parser("search", help="以關鍵字搜尋圖片")
    s.add_argument("query", nargs="*")
    s.add_argument("--limit", type=int, default=30)
    s.add_argument("--semantic", action="store_true", help="加上語意搜尋")
    s.add_argument("--json", action="store_true", help="輸出 JSON")
    s.add_argument("--paths", action="store_true", help="只輸出檔案完整路徑")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("tag", help="手動加入或移除標籤")
    s.add_argument("id", type=int)
    s.add_argument("--add", nargs="+")
    s.add_argument("--remove", nargs="+")
    s.add_argument("--note")
    s.set_defaults(func=cmd_tag)

    s = sub.add_parser("stats", help="圖庫統計")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("doctor", help="檢查 Ollama、模型與選用套件")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("config", help="查看或修改設定")
    s.add_argument("action", nargs="?", choices=["show", "set"], default="show")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.set_defaults(func=cmd_config)

    s = sub.add_parser("password", help="設定手機／平板連線密碼")
    s.set_defaults(func=cmd_password)

    s = sub.add_parser("serve", help="開啟圖庫介面")
    s.add_argument("--host", help="預設 127.0.0.1；開啟手機連線後為 0.0.0.0")
    s.add_argument("--port", type=int, help="預設 8765")
    s.add_argument("--open", action="store_true", help="自動開啟瀏覽器")
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows 主控台顯示中文
        except (AttributeError, ValueError):
            pass
    from .net import install_default_ca

    install_default_ca()
    args = build_parser().parse_args(argv)
    if args.command == "config" and args.action == "set" and (not args.key or args.value is None):
        print("用法：lumilib config set <key> <value>")
        return 1
    overrides = {"vision_model": args.vision_model, "ollama_url": args.ollama_url}
    if args.command == "config":
        overrides = {}  # 寫入設定時不要把一次性參數存進去
    cfg = load_config(args.home, **overrides)
    conn = db.connect(cfg.db_path)
    try:
        return args.func(conn, cfg, args)
    except ValueError as exc:
        print(f"錯誤：{exc}")
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass
