#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"

echo "========================================"
echo "  AI 网文脱水机"
echo "========================================"

# Check Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1)
        echo "  Python: $ver"
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  [ERROR] Python not found. Install Python >= 3.11"
    exit 1
fi

# Install dependencies if needed
if ! "$PYTHON" -c "import fastapi" 2>/dev/null; then
    echo ""
    echo "  Installing dependencies..."
    "$PYTHON" -m pip install -e . --quiet
    echo "  Done."
fi

# Ensure data directory
mkdir -p data

echo ""
echo "  Starting server at http://$HOST:$PORT"
echo "  首页:     http://$HOST:$PORT"
echo "  任务管理: http://$HOST:$PORT/static/task.html"
echo "  阅读器:   http://$HOST:$PORT/static/read.html"
echo "  Ctrl+C to stop"
echo "========================================"

# Open browser (macOS)
if command -v open &>/dev/null; then
    sleep 1 && open "http://$HOST:$PORT" &
fi

"$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
