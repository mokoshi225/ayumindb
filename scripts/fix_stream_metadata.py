"""既存ストリームの published_at / duration_sec を補完"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb.collector import get_video_info, COOKIE_FILE
from ayumindb.db import get_conn


def fix_missing_metadata(delay: float = 3.0):
    conn = get_conn()
    rows = conn.execute("""
        SELECT video_id, title, published_at, duration_sec, collection_status
        FROM streams
        WHERE published_at IS NULL OR duration_sec = 0
        ORDER BY published_at
    """).fetchall()
    conn.close()

    if not rows:
        print("✅ 全ストリームのメタデータは正常です")
        return

    print(f"📡 {len(rows)} 件のストリームを修正します")
    fixed_pub = 0
    fixed_dur = 0

    for i, r in enumerate(rows, 1):
        vid = r["video_id"]
        title = r["title"][:50]
        print(f"[{i}/{len(rows)}] {vid} {title}... ", end="", flush=True)

        info = get_video_info(vid, use_cookies=COOKIE_FILE.exists())
        if not info:
            print("⚠️ get_video_info 失敗")
            time.sleep(delay)
            continue

        from datetime import datetime

        pub = info.get("upload_date")
        duration = info.get("duration", 0)

        conn = get_conn()
        updated = False
        if pub and r["published_at"] is None:
            pub_dt = datetime.strptime(pub, "%Y%m%d")
            conn.execute(
                "UPDATE streams SET published_at = ? WHERE video_id = ? AND published_at IS NULL",
                (pub_dt.isoformat(), vid),
            )
            fixed_pub += 1
            updated = True
        if duration and r["duration_sec"] == 0:
            conn.execute(
                "UPDATE streams SET duration_sec = ? WHERE video_id = ? AND duration_sec = 0",
                (duration, vid),
            )
            fixed_dur += 1
            updated = True
        conn.commit()
        conn.close()

        if updated:
            print(f"✅ published_at={pub!r}, duration_sec={duration}")
        else:
            print("→ 変更なし")

        time.sleep(delay)

    print(f"\n🎉 完了: published_at={fixed_pub}件, duration_sec={fixed_dur}件")


if __name__ == "__main__":
    fix_missing_metadata()
