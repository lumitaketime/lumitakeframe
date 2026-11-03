# PyInstaller 設定：把 lumilib 與所有相依套件打包成一個資料夾（啟動比單一檔案快）
# 用法：pyinstaller --noconfirm lumilib-server.spec
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("onnxruntime", "tokenizers", "pillow_heif", "imageio_ffmpeg", "certifi"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass
# 網頁介面與離線地名資料（直接從原始碼資料夾收集）
for sub in ("web", "web/assets", "web/icons", "data"):
    src = os.path.join(os.path.abspath(os.path.join(SPECPATH, "..", "..")), "lumilib", sub)
    if os.path.isdir(src):
        datas += [(os.path.join(src, f), os.path.join("lumilib", sub)) for f in os.listdir(src)
                  if os.path.isfile(os.path.join(src, f))]
hiddenimports += collect_submodules("uvicorn") + collect_submodules("lumilib")
hiddenimports += ["send2trash", "qrcode.image.svg", "numpy"]

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))  # image-library/

a = Analysis(
    ["lumilib_server.py"],
    pathex=[ROOT],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "pandas", "geonamescache", "gi", "PyQt5", "PyQt6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lumilib-server", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="lumilib-server", upx=False)
