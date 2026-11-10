#!/bin/bash
# Re'memor 一鍵安裝（macOS，Apple Silicon / Intel）
# 用法：在終端機執行  bash install-mac.sh
set -euo pipefail

cd "$(dirname "$0")"
APP_DIR="$(pwd)"
DEFAULT_MODEL="qwen2.5vl:7b"

say() { printf "\n\033[1;34m▸ %s\033[0m\n" "$1"; }
ok() { printf "  \033[32m✓\033[0m %s\n" "$1"; }

if [[ "$(uname)" != "Darwin" ]]; then
  echo "這個安裝程式只支援 macOS。"
  exit 1
fi

say "1/5 檢查 Homebrew（Mac 的套件管理工具）"
if ! command -v brew >/dev/null 2>&1; then
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [[ -x "$p" ]] && eval "$("$p" shellenv)"
  done
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "  尚未安裝 Homebrew，接下來會安裝（過程中需要輸入 Mac 的登入密碼）。"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [[ -x "$p" ]] && eval "$("$p" shellenv)"
  done
fi
ok "Homebrew $(brew --version | head -1 | awk '{print $2}')"

say "2/5 安裝 Python、exiftool（讀取 EXIF／RAW）、ffmpeg（影片）"
brew install python@3.12 exiftool ffmpeg
PY="$(brew --prefix python@3.12)/bin/python3.12"
ok "$("$PY" --version)、exiftool $(exiftool -ver)、ffmpeg"

say "3/5 安裝 Ollama（在這台 Mac 上執行 AI 模型）"
if ! command -v ollama >/dev/null 2>&1 && [[ ! -d /Applications/Ollama.app ]]; then
  brew install ollama
fi
if ! curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  if [[ -d /Applications/Ollama.app ]]; then
    open -a Ollama
  else
    brew services start ollama
  fi
  for _ in $(seq 1 20); do
    curl -s --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null && break
    sleep 1
  done
fi
if curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  ok "Ollama 已啟動"
else
  echo "  ⚠ Ollama 沒有回應，可稍後在終端機執行：brew services start ollama"
fi

say "4/5 建立 Re'memor 執行環境"
"$PY" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -e "$APP_DIR"
ok "已安裝到 $APP_DIR/.venv"

LAUNCHER="$HOME/Desktop/Re'memor.command"
cat > "$LAUNCHER" <<LAUNCH
#!/bin/bash
# 點兩下啟動 Re'memor；關閉這個視窗就會停止。
# 想把圖庫資料（資料庫與縮圖）放在外接 SSD，取消下一行的註解並改成你的路徑：
# export REMEMOR_HOME="/Volumes/你的SSD/.rememor"
cd "$APP_DIR"
echo "Re'memor 執行中，瀏覽器會自動開啟。關閉這個視窗即停止。"
# caffeinate：接電源時避免 Mac 睡眠，手機才能持續連線
exec caffeinate -is "$APP_DIR/.venv/bin/python" -m lumilib serve --open
LAUNCH
chmod +x "$LAUNCHER"
ok "桌面捷徑：Re'memor.command"

say "5/5 下載 AI 視覺模型"
if command -v ollama >/dev/null 2>&1 && ollama list 2>/dev/null | grep -q "^${DEFAULT_MODEL}"; then
  ok "$DEFAULT_MODEL 已下載"
else
  read -r -p "  要現在下載推薦模型 $DEFAULT_MODEL（約 6 GB）嗎？也可以稍後在設定頁下載。[Y/n] " ans
  if [[ -z "$ans" || "$ans" =~ ^[Yy] ]]; then
    ollama pull "$DEFAULT_MODEL" && ok "$DEFAULT_MODEL 下載完成"
  else
    echo "  略過。之後到「設定 → AI 模型」按下載即可。"
  fi
fi

printf "\n\033[1;32m安裝完成！\033[0m\n"
echo "  • 點兩下桌面上的「Re'memor.command」啟動"
echo "  • 第一次開啟到「設定」加入照片資料夾（練習可先加入 ~/Pictures）"
echo
read -r -p "現在啟動嗎？[Y/n] " start
if [[ -z "$start" || "$start" =~ ^[Yy] ]]; then
  open "$LAUNCHER"
fi
