"""リアルタイムライブ監視 — 新着配信を検知してチャットを自動収集"""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb import VERSION
from ayumindb.collector import check_live, start_live_capture, CHAT_DIR, COOKIE_FILE
from ayumindb.parser import parse_chat_file
from ayumindb.db import (
    init_db, get_stream, upsert_stream, upsert_viewer,
    insert_comments_batch, insert_membership_event,
    update_stream_collection_status, Stream,
)

JST = timezone(timedelta(hours=9))
POLL_INTERVAL = 300  # 5分
CAPTURE_PROCESSES: dict[str, any] = {}  # video_id -> Popen


def log(msg: str):
    ts = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def finish_capture(video_id: str, title: str):
    """キャプチャ完了処理 — チャットファイルをパースしてDBに取り込み"""
    chat_file = CHAT_DIR / f"{video_id}.live_chat.json"
    if not chat_file.exists():
        log(f"  ⚠️ {video_id}: チャットファイルなし")
        update_stream_collection_status(video_id, "no_chat")
        return

    # 配信終了後、チャットリプレイが使えるならフル取得で上書き
    import subprocess as sp
    cmd = [
        "yt-dlp", "--write-subs", "--sub-langs", "live_chat",
        "--skip-download", "--ignore-no-formats-error",
        "--sleep-requests", "2",
        "-o", str(CHAT_DIR / "%(id)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    if COOKIE_FILE.exists():
        cmd[1:1] = ["--cookies", str(COOKIE_FILE)]
    sp.run(cmd, capture_output=True, text=True, timeout=300)

    try:
        result = parse_chat_file(chat_file)
        for v in result["viewers"].values():
            upsert_viewer(v)
        if result["comments"]:
            insert_comments_batch(result["comments"])
        for e in result["membership_events"]:
            insert_membership_event(e)
        update_stream_collection_status(
            video_id, "completed",
            len(result["comments"]), len(result["viewers"]),
        )
        log(f"  ✅ {title[:40]}: {len(result['comments'])} comments, {len(result['viewers'])} viewers")
    except Exception as e:
        update_stream_collection_status(video_id, "error")
        log(f"  ❌ {title[:40]}: parse error — {e}")


def main_loop():
    init_db()
    log(f"AyumiDB v{VERSION} ライブ監視開始（{POLL_INTERVAL}秒間隔）")

    while True:
        try:
            live_streams = check_live()
        except Exception as e:
            log(f"⚠️ ライブチェック失敗: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        live_ids = {s["id"] for s in live_streams}

        # --- 新規ライブ配信の検出 ---
        for s in live_streams:
            vid = s["id"]
            title = s.get("title", "")
            existing = get_stream(vid)

            if existing and existing.collection_status == "completed":
                continue
            if vid in CAPTURE_PROCESSES:
                proc = CAPTURE_PROCESSES[vid]
                if proc.poll() is None:
                    continue  # 既に追跡中
                # プロセスが死んでいたら回収
                del CAPTURE_PROCESSES[vid]

            is_member_only = "メン限" in title or "メンバーシップ" in title
            use_cookies = is_member_only and COOKIE_FILE.exists()

            log(f"🔴 LIVE detected: {title[:50]}")
            upsert_stream(Stream(
                video_id=vid, title=title,
                is_member_only=is_member_only,
            ))

            try:
                proc = start_live_capture(vid, use_cookies=use_cookies)
                CAPTURE_PROCESSES[vid] = proc
                log(f"  📡 キャプチャ開始 (PID {proc.pid})")
            except Exception as e:
                log(f"  ❌ キャプチャ起動失敗: {e}")

        # --- 終了したライブ配信の処理 ---
        finished = [vid for vid, proc in CAPTURE_PROCESSES.items()
                    if vid not in live_ids and proc.poll() is not None]
        for vid in finished:
            s = get_stream(vid)
            title = s.title if s else vid
            log(f"📴 Stream ended: {title[:50]}")
            finish_capture(vid, title)
            del CAPTURE_PROCESSES[vid]

        # --- ライブ一覧に無いがプロセスが動いてる場合（検知漏れ対策） ---
        orphaned = [vid for vid, proc in CAPTURE_PROCESSES.items()
                    if vid not in live_ids and proc.poll() is not None]
        for vid in orphaned:
            s = get_stream(vid)
            title = s.title if s else vid
            log(f"🔄 Orphaned capture ending: {title[:50]}")
            finish_capture(vid, title)
            del CAPTURE_PROCESSES[vid]

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        log("👋 監視終了")
        for vid, proc in CAPTURE_PROCESSES.items():
            proc.terminate()
        sys.exit(0)
