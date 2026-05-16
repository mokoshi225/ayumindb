"""既存ストリームに stream_started_at をバックフィルするマイグレーション"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb.db import init_db, get_conn

def migrate():
    init_db()
    conn = get_conn()

    # stream_started_at が未設定の completed ストリームを取得
    rows = conn.execute("""
        SELECT s.video_id, MIN(c.published_at) as first_comment
        FROM streams s
        JOIN comments c ON c.stream_id = s.video_id
        WHERE s.collection_status = 'completed'
          AND s.stream_started_at IS NULL
        GROUP BY s.video_id
    """).fetchall()

    print(f"Found {len(rows)} streams to migrate")

    updated = 0
    for r in rows:
        conn.execute(
            "UPDATE streams SET stream_started_at = ? WHERE video_id = ?",
            (r["first_comment"], r["video_id"]),
        )
        updated += 1
        if updated % 10 == 0:
            print(f"  {updated}/{len(rows)}...")
            conn.commit()

    conn.commit()
    conn.close()
    print(f"✅ Done: {updated} streams updated with stream_started_at")

if __name__ == "__main__":
    migrate()
