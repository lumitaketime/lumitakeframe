"""Mac App 內建伺服器的進入點（PyInstaller 打包用）。"""

import multiprocessing
import sys

from lumilib.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
