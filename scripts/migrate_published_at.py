"""配信の published_at 訂正マイグレーション

症状: 過去の配信なのに published_at がデータ取得日（2026-05-16 など）に
なっている。これは _extract_stream_date() が .live_chat.json の1行目
（liveChatViewerEngagementMessageRenderer = 取得時のタイムスタンプ）を
読んでいたバグによるもの。

修正: stream_started_at（最初のコメントから正しくパースされた日時）の
日付部分で published_at を上書きする。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb.db import init_db, get_conn


def migrate():
    init_db()
    conn = get_conn()

    # published_at にマイクロ秒を含む = _extract_stream_date() 由来 = 誤った日付
    rows = conn.execute("""
        SELECT s.video_id, s.published_at, s.stream_started_at
        FROM streams s
        WHERE s.published_at LIKE '%.%'
    """).fetchall()

    print(f"Found {len(rows)} streams with microsecond-precision published_at (bug signature)")

    updated = 0
    for r in rows:
        video_id = r["video_id"]
        started = r["stream_started_at"]

        if started:
            # stream_started_at から日付部分だけ使う
            conn.execute(
                "UPDATE streams SET published_at = ? WHERE video_id = ?",
                (started[:10] + "T00:00:00", video_id),
            )
            updated += 1
        else:
            # stream_started_at がない → comments テーブルから最初のコメントを探す
            first = conn.execute("""
                SELECT MIN(c.published_at) as first_ts
                FROM comments c
                WHERE c.stream_id = ?
            """, (video_id,)).fetchone()
            if first and first["first_ts"]:
                conn.execute(
                    "UPDATE streams SET published_at = ? WHERE video_id = ?",
                    (first["first_ts"][:10] + "T00:00:00", video_id),
                )
                updated += 1
                print(f"  ⚠️ {video_id}: stream_started_at がなく、comments から補完")
            else:
                print(f"  ⚠️ {video_id}: 訂正不可（stream_started_at も comments もなし）")

    conn.commit()
    conn.close()
    print(f"✅ Done: {updated} streams fixed")


if __name__ == "__main__":
    migrate()
