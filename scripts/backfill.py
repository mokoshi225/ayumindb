"""初回バックフィル — チャンネルの全配信をリストアップし、チャットを順次収集"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb import VERSION
from ayumindb.collector import get_channel_streams, download_chat, get_video_info, COOKIE_FILE
from ayumindb.parser import parse_chat_file
from ayumindb.db import (
    init_db, get_conn, upsert_stream, upsert_viewer, insert_comments_batch,
    insert_membership_event, update_stream_collection_status, get_stream,
    recompute_viewer_stats, Stream as DBStream,
)
from datetime import datetime


def import_chat_to_db(filepath: Path, use_cookies: bool):
    result = parse_chat_file(filepath)
    video_id = result["stream_id"]

    s = get_stream(video_id)
    if s:
        s.chat_count = len(result["comments"])
        s.unique_viewers = len(result["viewers"])
        update_stream_collection_status(
            video_id, "completed",
            len(result["comments"]), len(result["viewers"]),
        )

    # 配信日時を補完（parse_chat_file の結果から最初のコメントの日付を使う）
    if s and not s.published_at and result["comments"]:
        first_ts = result["comments"][0].published_at
        conn = get_conn()
        conn.execute("UPDATE streams SET published_at = ? WHERE video_id = ?",
                     (first_ts.isoformat(), video_id))
        conn.commit()
        conn.close()

    # 配信の実際の開始時刻を最初のコメントから設定（time_offset の基準）
    if result["comments"]:
        first_ts = result["comments"][0].published_at
        conn = get_conn()
        conn.execute("UPDATE streams SET stream_started_at = ? WHERE video_id = ?",
                     (first_ts.isoformat(), video_id))
        conn.commit()
        conn.close()

    for v in result["viewers"].values():
        upsert_viewer(v)

    if result["comments"]:
        insert_comments_batch(result["comments"])

    for e in result["membership_events"]:
        insert_membership_event(e)

    return len(result["comments"]), len(result["viewers"]), len(result["membership_events"])


def backfill(batch_size: int = 20, delay: float = 5.0):
    print(f"AyumiDB v{VERSION} — あゆみんch バックフィル")
    init_db()

    cookie_available = COOKIE_FILE.exists()
    if cookie_available:
        print(f"✅ Cookie file found: {COOKIE_FILE}")
    else:
        print("⚠️  No cookie file. Run 'python scripts/export_cookies.py' first.")

    stream_list_raw = get_channel_streams()
    print(f"📡 Total stream entries: {len(stream_list_raw)}")

    total_comments = 0
    total_viewers = 0
    total_membership = 0
    processed = 0
    skipped = 0

    for entry in stream_list_raw:
        video_id = entry["id"]
        title = entry.get("title", "")
        duration = entry.get("duration", 0)
        url = entry.get("url", "")

        existing = get_stream(video_id)
        if existing and existing.collection_status == "completed":
            skipped += 1
            continue

        info = get_video_info(video_id, use_cookies=cookie_available)
        is_member_only = info.get("availability") in ("members_only", "subscriber_only")
        if not is_member_only:
            is_member_only = any(kw in title for kw in ("メン限", "メンバーシップ", "メンバー限定", "有料サブスク", "サブスク限定"))
        use_cookies = is_member_only and cookie_available
        pub = info.get("upload_date")
        if pub:
            pub_dt = datetime.strptime(pub, "%Y%m%d")
        else:
            pub_dt = None

        s = DBStream(
            video_id=video_id,
            title=title,
            published_at=pub_dt,
            duration_sec=duration,
            is_member_only=is_member_only,
        )
        upsert_stream(s)

        print(f"[{processed + 1}/{len(stream_list_raw)}] {title[:50]}... ", end="", flush=True)

        chat_file = download_chat(video_id, use_cookies=use_cookies)
        if not chat_file and not use_cookies and cookie_available:
            chat_file = download_chat(video_id, use_cookies=True)
            if chat_file:
                is_member_only = True
                conn = get_conn()
                conn.execute("UPDATE streams SET is_member_only = 1 WHERE video_id = ?", (video_id,))
                conn.commit()
                conn.close()
                use_cookies = True
        if not chat_file:
            update_stream_collection_status(video_id, "no_chat")
            print("⚠️ No chat")
            processed += 1
            continue

        try:
            cc, vc, mc = import_chat_to_db(chat_file, use_cookies)
            total_comments += cc
            total_viewers += vc
            total_membership += mc
            print(f"✅ {cc} comments, {vc} viewers, {mc} membership events")
        except Exception as e:
            update_stream_collection_status(video_id, "error")
            print(f"❌ Error: {e}")

        processed += 1

        if processed % batch_size == 0:
            wait = min(delay * 3, 60)
            print(f"--- Batch pause: {wait:.0f}s ---")
            time.sleep(wait)
        else:
            time.sleep(delay)

    print(f"\n{'='*40}")
    print(f"🎉 Done! Processed: {processed}, Skipped: {skipped}")
    print(f"   Total comments: {total_comments}")
    print(f"   Total viewers:  {total_viewers}")
    print(f"   Total membership events: {total_membership}")
    print(f"🔄 Recomputing viewer stats...")
    recompute_viewer_stats()
    print(f"✅ Viewer stats updated")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill ayumindb with YouTube live chat data")
    parser.add_argument("--batch", type=int, default=20, help="Batch size before long pause")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay between requests (seconds)")
    args = parser.parse_args()
    backfill(batch_size=args.batch, delay=args.delay)
