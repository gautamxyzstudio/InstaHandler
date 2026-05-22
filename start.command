#!/bin/bash
# Double-click this file to launch MOZART Insta Handler on macOS.
# If double-click doesn't work, see "First-time fix" in README.md.

cd "$(dirname "$0")"

# pretty banner
echo ""
echo "============================================"
echo "    MOZART Insta Handler"
echo "============================================"
echo ""

# 1. find python3
PY=""
for candidate in python3 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "ERROR: Python 3 is not installed."
  echo ""
  echo "Install it with one of:"
  echo "  1. Open Terminal and run:  xcode-select --install"
  echo "  2. Or download from:       https://www.python.org/downloads/macos/"
  echo ""
  read -p "Press Enter to close..."
  exit 1
fi

echo "Using Python: $PY"
"$PY" --version
echo ""

# 2. install deps if any are missing (checks every required module)
NEEDED="flask requests google.auth google.oauth2 googleapiclient"
MISSING=0
for mod in $NEEDED; do
  if ! "$PY" -c "import $mod" 2>/dev/null; then
    MISSING=1
    break
  fi
done

if [ $MISSING -eq 1 ]; then
  echo "Installing dependencies..."
  "$PY" -m pip install --user -r requirements.txt
  if [ $? -ne 0 ]; then
    echo ""
    echo "pip install failed. Trying with --break-system-packages..."
    "$PY" -m pip install --user --break-system-packages -r requirements.txt
  fi
  echo ""
fi

# 3. run
echo "Starting app... (browser will open in a moment)"
echo "  URL:  http://127.0.0.1:5050"
echo ""
echo "  >> Keep this window open while using the app."
echo "  >> Press Ctrl+C (or close this window) to stop."
echo ""

"$PY" app.py

echo ""
read -p "App stopped. Press Enter to close..."
