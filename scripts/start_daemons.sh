#!/bin/bash
# AyumiDB デーモン起動スクリプト
# .bashrc または WSL2 起動時に実行されることを想定

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$SCRIPT_DIR/data"
mkdir -p "$LOG_DIR"

# バックフィルが動いていなければ起動
if ! tmux has-session -t ayumindb 2>/dev/null; then
    tmux new-session -d -s ayumindb -c "$SCRIPT_DIR" \
        "python3 -u scripts/backfill.py --batch 20 --delay 5 > $LOG_DIR/backfill.log 2>&1"
    echo "Backfill started in tmux session 'ayumindb'"
fi

# ライブモニターが動いていなければ起動
if ! tmux has-session -t monitor 2>/dev/null; then
    tmux new-session -d -s monitor -c "$SCRIPT_DIR" \
        "python3 -u scripts/live_monitor.py > $LOG_DIR/monitor.log 2>&1"
    echo "Monitor started in tmux session 'monitor'"
fi

# Streamlit ダッシュボードが動いていなければ起動
if ! tmux has-session -t dashboard 2>/dev/null; then
    tmux new-session -d -s dashboard -c "$SCRIPT_DIR" \
        "streamlit run ayumindb/app.py --server.headless true > $LOG_DIR/dashboard.log 2>&1"
    echo "Dashboard started in tmux session 'dashboard' (http://localhost:8501)"
fi
