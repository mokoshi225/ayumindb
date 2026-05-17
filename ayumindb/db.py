"""SQLite データベース操作"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Comment, MembershipEvent, Stream, Viewer

DB_PATH = Path(__file__).parent.parent / "data" / "ayumindb.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS viewers (
    channel_id      TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL DEFAULT '',
    avatar_url      TEXT NOT NULL DEFAULT '',
    first_seen_at   TEXT,
    is_member       INTEGER NOT NULL DEFAULT 0,
    first_member_at TEXT,
    is_owner        INTEGER NOT NULL DEFAULT 0,
    is_moderator    INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS streams (
    video_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    published_at    TEXT,
    stream_started_at TEXT,
    live_chat_id    TEXT NOT NULL DEFAULT '',
    duration_sec    INTEGER NOT NULL DEFAULT 0,
    chat_count      INTEGER NOT NULL DEFAULT 0,
    unique_viewers  INTEGER NOT NULL DEFAULT 0,
    is_member_only  INTEGER NOT NULL DEFAULT 0,
    collection_status TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      TEXT NOT NULL,
    viewer_id       TEXT NOT NULL REFERENCES viewers(channel_id),
    stream_id       TEXT NOT NULL REFERENCES streams(video_id),
    published_at    TEXT NOT NULL,
    message_text    TEXT NOT NULL DEFAULT '',
    message_type    TEXT NOT NULL DEFAULT 'textMessageEvent',
    is_member       INTEGER NOT NULL DEFAULT 0,
    super_chat_amount_text TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(message_id)
);

CREATE INDEX IF NOT EXISTS idx_comments_viewer ON comments(viewer_id);
CREATE INDEX IF NOT EXISTS idx_comments_stream ON comments(stream_id);
CREATE INDEX IF NOT EXISTS idx_comments_published ON comments(published_at);

CREATE TABLE IF NOT EXISTS membership_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    viewer_id       TEXT NOT NULL REFERENCES viewers(channel_id),
    stream_id       TEXT NOT NULL REFERENCES streams(video_id),
    event_type      TEXT NOT NULL,
    member_level    TEXT NOT NULL DEFAULT '',
    member_month    INTEGER NOT NULL DEFAULT 0,
    occurred_at     TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_membership_viewer ON membership_events(viewer_id);

CREATE TABLE IF NOT EXISTS collection_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_id       TEXT REFERENCES streams(video_id),
    collection_type TEXT NOT NULL,
    status          TEXT NOT NULL,
    message_count   INTEGER DEFAULT 0,
    error_message   TEXT DEFAULT '',
    collected_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA_SQL)
    # Migration: add materialized viewer stats columns (idempotent)
    for col in (
        "ALTER TABLE viewers ADD COLUMN comment_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE viewers ADD COLUMN superchat_total INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(col)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()


# ---- Viewer operations ----

def recompute_viewer_stats():
    """Recompute and store comment_count / superchat_total for all viewers from actual comment data."""
    conn = get_conn()
    conn.execute("""
        UPDATE viewers SET
            comment_count = (SELECT COUNT(*) FROM comments c WHERE c.viewer_id = viewers.channel_id),
            superchat_total = COALESCE(
                (SELECT SUM(CAST(REPLACE(REPLACE(c.super_chat_amount_text, '¥', ''), ',', '') AS INTEGER))
                 FROM comments c
                 WHERE c.viewer_id = viewers.channel_id AND c.message_type = 'superChatEvent'), 0)
    """)
    conn.commit()
    conn.close()


def upsert_viewer(v: Viewer):
    conn = get_conn()
    conn.execute("""
        INSERT INTO viewers (channel_id, display_name, avatar_url, first_seen_at, is_member,
                             first_member_at, is_owner, is_moderator, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(channel_id) DO UPDATE SET
            display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), viewers.display_name),
            avatar_url   = COALESCE(NULLIF(EXCLUDED.avatar_url, ''),   viewers.avatar_url),
            first_seen_at = MIN(viewers.first_seen_at, EXCLUDED.first_seen_at),
            is_member    = MAX(viewers.is_member, EXCLUDED.is_member),
            first_member_at = COALESCE(viewers.first_member_at, EXCLUDED.first_member_at),
            is_owner     = MAX(viewers.is_owner, EXCLUDED.is_owner),
            is_moderator = MAX(viewers.is_moderator, EXCLUDED.is_moderator),
            updated_at   = datetime('now')
    """, (
        v.channel_id, v.display_name, v.avatar_url,
        v.first_seen_at.isoformat() if v.first_seen_at else None,
        int(v.is_member),
        v.first_member_at.isoformat() if v.first_member_at else None,
        int(v.is_owner), int(v.is_moderator),
    ))
    conn.commit()
    conn.close()


def get_all_viewers() -> list[Viewer]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT v.* FROM viewers v
        ORDER BY v.first_seen_at ASC
    """).fetchall()
    conn.close()
    return [_row_to_viewer(r) for r in rows]


def get_viewer(channel_id: str) -> Optional[Viewer]:
    conn = get_conn()
    r = conn.execute("""
        SELECT v.* FROM viewers v WHERE v.channel_id = ?
    """, (channel_id,)).fetchone()
    conn.close()
    return _row_to_viewer(r) if r else None


def _row_to_viewer(r) -> Viewer:
    return Viewer(
        channel_id=r["channel_id"],
        display_name=r["display_name"],
        avatar_url=r["avatar_url"],
        first_seen_at=_parse_dt(r["first_seen_at"]),
        is_member=bool(r["is_member"]),
        first_member_at=_parse_dt(r["first_member_at"]),
        is_owner=bool(r["is_owner"]),
        is_moderator=bool(r["is_moderator"]),
        comment_count=r["comment_count"],
        superchat_total=r["superchat_total"],
    )


# ---- Stream operations ----

def upsert_stream(s: Stream):
    conn = get_conn()
    conn.execute("""
        INSERT INTO streams (video_id, title, published_at, stream_started_at, live_chat_id, duration_sec,
                             chat_count, unique_viewers, is_member_only, collection_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ON CONFLICT(video_id) DO UPDATE SET
            title = COALESCE(NULLIF(EXCLUDED.title, ''), streams.title),
            published_at = COALESCE(NULLIF(EXCLUDED.published_at, ''), streams.published_at),
            stream_started_at = COALESCE(EXCLUDED.stream_started_at, streams.stream_started_at),
            duration_sec = EXCLUDED.duration_sec,
            is_member_only = EXCLUDED.is_member_only
    """, (s.video_id, s.title,
          s.published_at.isoformat() if s.published_at else None,
          s.stream_started_at.isoformat() if s.stream_started_at else None,
          s.live_chat_id, s.duration_sec, s.chat_count, s.unique_viewers, int(s.is_member_only)))
    conn.commit()
    conn.close()


def get_all_streams() -> list[Stream]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.* FROM streams s
        ORDER BY s.published_at DESC
    """).fetchall()
    conn.close()
    return [_row_to_stream(r) for r in rows]


def get_stream(video_id: str) -> Optional[Stream]:
    conn = get_conn()
    r = conn.execute("""
        SELECT s.* FROM streams s WHERE s.video_id = ?
    """, (video_id,)).fetchone()
    conn.close()
    return _row_to_stream(r) if r else None


def get_pending_streams() -> list[Stream]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.*, 0 as chat_count, 0 as unique_viewers
        FROM streams s
        WHERE s.collection_status = 'pending'
        ORDER BY s.published_at ASC
    """).fetchall()
    conn.close()
    return [_row_to_stream(r) for r in rows]


def update_stream_collection_status(video_id: str, status: str, chat_count: int = 0, unique_viewers: int = 0):
    conn = get_conn()
    conn.execute("""
        UPDATE streams SET collection_status = ?, chat_count = ?, unique_viewers = ? WHERE video_id = ?
    """, (status, chat_count, unique_viewers, video_id))
    conn.commit()
    conn.close()


def _row_to_stream(r) -> Stream:
    return Stream(
        video_id=r["video_id"],
        title=r["title"],
        published_at=_parse_dt(r["published_at"]),
        stream_started_at=_parse_dt(r["stream_started_at"]),
        live_chat_id=r["live_chat_id"],
        duration_sec=r["duration_sec"],
        chat_count=r["chat_count"],
        unique_viewers=r["unique_viewers"],
        is_member_only=bool(r["is_member_only"]),
        collection_status=r["collection_status"],
    )


# ---- Comment operations ----

def insert_comment(c: Comment):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO comments
                (message_id, viewer_id, stream_id, published_at, message_text, message_type, is_member, super_chat_amount_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (c.message_id, c.viewer_id, c.stream_id,
              c.published_at.isoformat(), c.message_text, c.message_type,
              int(c.is_member), c.super_chat_amount_text))
        # Increment viewer aggregates
        amount = _parse_superchat_amount(c.super_chat_amount_text)
        conn.execute("""
            UPDATE viewers SET
                comment_count = comment_count + 1,
                superchat_total = superchat_total + ?
            WHERE channel_id = ?
        """, (amount, c.viewer_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # duplicate message_id
    finally:
        conn.close()


def _parse_superchat_amount(text: str) -> int:
    """Parse '¥15,800' -> 15800. Returns 0 on failure."""
    if not text:
        return 0
    try:
        return int(text.replace('¥', '').replace(',', ''))
    except (ValueError, TypeError):
        return 0


def insert_comments_batch(comments: list[Comment]):
    conn = get_conn()
    rows = [
        (c.message_id, c.viewer_id, c.stream_id, c.published_at.isoformat(),
         c.message_text, c.message_type, int(c.is_member), c.super_chat_amount_text)
        for c in comments
    ]
    conn.executemany("""
        INSERT OR IGNORE INTO comments
            (message_id, viewer_id, stream_id, published_at, message_text, message_type, is_member, super_chat_amount_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    # Increment viewer aggregates per viewer
    viewer_deltas: dict[str, dict[str, int]] = {}
    for c in comments:
        if c.viewer_id not in viewer_deltas:
            viewer_deltas[c.viewer_id] = {"count": 0, "superchat": 0}
        viewer_deltas[c.viewer_id]["count"] += 1
        viewer_deltas[c.viewer_id]["superchat"] += _parse_superchat_amount(c.super_chat_amount_text)
    for vid, delta in viewer_deltas.items():
        conn.execute("""
            UPDATE viewers SET
                comment_count = comment_count + ?,
                superchat_total = superchat_total + ?
            WHERE channel_id = ?
        """, (delta["count"], delta["superchat"], vid))
    conn.commit()
    conn.close()


def get_comments_by_viewer(viewer_id: str, limit: int = 0) -> list[tuple[Comment, str, int]]:
    conn = get_conn()
    sql = """
        SELECT c.*, s.video_id,
               CAST(COALESCE(strftime('%s', c.published_at), '0') AS INTEGER)
               - CAST(COALESCE(strftime('%s', COALESCE(s.stream_started_at, s.published_at)), '0') AS INTEGER) as time_offset
        FROM comments c
        JOIN streams s ON c.stream_id = s.video_id
        WHERE c.viewer_id = ?
        ORDER BY c.published_at DESC
    """
    params: list = [viewer_id]
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [(_row_to_comment(r), r["video_id"], r["time_offset"]) for r in rows]


def get_comments_by_stream(stream_id: str, limit: int = 0) -> list[Comment]:
    conn = get_conn()
    sql = """
        SELECT c.* FROM comments c WHERE c.stream_id = ?
        ORDER BY c.published_at ASC
    """
    params: list = [stream_id]
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_comment(r) for r in rows]


def search_comments(query: str, limit: int = 0) -> list[tuple[Comment, str, int, str]]:
    conn = get_conn()
    sql = """
        SELECT c.*, s.video_id, v.display_name,
               CAST(COALESCE(strftime('%s', c.published_at), '0') AS INTEGER)
               - CAST(COALESCE(strftime('%s', COALESCE(s.stream_started_at, s.published_at)), '0') AS INTEGER) as time_offset
        FROM comments c
        JOIN streams s ON c.stream_id = s.video_id
        JOIN viewers v ON c.viewer_id = v.channel_id
        WHERE c.message_text LIKE ?
        ORDER BY c.published_at DESC
    """
    params: list = [f"%{query}%"]
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [(_row_to_comment(r), r["video_id"], r["time_offset"], r["display_name"]) for r in rows]


def _row_to_comment(r) -> Comment:
    return Comment(
        message_id=r["message_id"],
        viewer_id=r["viewer_id"],
        stream_id=r["stream_id"],
        published_at=datetime.fromisoformat(r["published_at"]),
        message_text=r["message_text"],
        message_type=r["message_type"],
        is_member=bool(r["is_member"]),
        super_chat_amount_text=r["super_chat_amount_text"],
    )


# ---- Membership events ----

def insert_membership_event(e: MembershipEvent):
    conn = get_conn()
    conn.execute("""
        INSERT INTO membership_events (viewer_id, stream_id, event_type, member_level, member_month, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (e.viewer_id, e.stream_id, e.event_type, e.member_level, e.member_month,
          e.occurred_at.isoformat()))
    conn.commit()
    conn.close()


def get_membership_events_by_viewer(viewer_id: str) -> list[MembershipEvent]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM membership_events WHERE viewer_id = ?
        ORDER BY occurred_at ASC
    """, (viewer_id,)).fetchall()
    conn.close()
    return [_row_to_membership(r) for r in rows]


def _row_to_membership(r) -> MembershipEvent:
    return MembershipEvent(
        viewer_id=r["viewer_id"],
        stream_id=r["stream_id"],
        event_type=r["event_type"],
        member_level=r["member_level"],
        member_month=r["member_month"],
        occurred_at=datetime.fromisoformat(r["occurred_at"]),
    )


# ---- Time-series analytics ----

def get_stream_time_series(stream_id: str, bucket_sec: int = 300) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            CAST(
                (CAST(strftime('%s', c.published_at) AS INTEGER)
                 - CAST(strftime('%s', COALESCE(s.stream_started_at, s.published_at)) AS INTEGER))
                / ? AS INTEGER) * ? AS bucket_start,
            COUNT(*) AS comment_count,
            COUNT(DISTINCT c.viewer_id) AS viewer_count
        FROM comments c
        JOIN streams s ON c.stream_id = s.video_id
        WHERE c.stream_id = ?
        GROUP BY bucket_start
        ORDER BY bucket_start
    """, (bucket_sec, bucket_sec, stream_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_overall_time_series() -> dict:
    conn = get_conn()
    monthly_comments = conn.execute("""
        SELECT strftime('%Y-%m', published_at) AS month, COUNT(*) AS cnt
        FROM comments GROUP BY month ORDER BY month
    """).fetchall()
    monthly_viewers = conn.execute("""
        SELECT strftime('%Y-%m', published_at) AS month, COUNT(DISTINCT viewer_id) AS cnt
        FROM comments GROUP BY month ORDER BY month
    """).fetchall()
    monthly_streams = conn.execute("""
        SELECT strftime('%Y-%m', published_at) AS month, COUNT(*) AS cnt
        FROM streams GROUP BY month ORDER BY month
    """).fetchall()
    conn.close()
    return {
        "comments": [dict(r) for r in monthly_comments],
        "viewers": [dict(r) for r in monthly_viewers],
        "streams": [dict(r) for r in monthly_streams],
    }


# ---- Helpers ----

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if s:
        try:
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            pass
    return None


def get_stats() -> dict:
    conn = get_conn()
    stats = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM viewers) as viewer_count,
            (SELECT COUNT(*) FROM viewers WHERE is_member = 1) as member_count,
            (SELECT COUNT(*) FROM streams) as stream_count,
            (SELECT COUNT(*) FROM comments) as comment_count,
            (SELECT COUNT(*) FROM comments WHERE message_type = 'superChatEvent') as superchat_count
    """).fetchone()
    conn.close()
    return dict(stats)


def get_rankings(rank_type: str, limit: int = 50) -> list[dict]:
    conn = get_conn()
    if rank_type == "oldest":
        rows = conn.execute("""
            SELECT v.channel_id, v.display_name, v.first_seen_at, v.comment_count
            FROM viewers v
            WHERE v.is_owner = 0
            ORDER BY v.first_seen_at ASC LIMIT ?
        """, (limit,)).fetchall()
    elif rank_type == "comments":
        rows = conn.execute("""
            SELECT v.channel_id, v.display_name, v.first_seen_at, v.comment_count
            FROM viewers v
            WHERE v.is_owner = 0
            ORDER BY v.comment_count DESC LIMIT ?
        """, (limit,)).fetchall()
    elif rank_type == "superchat":
        rows = conn.execute("""
            SELECT v.channel_id, v.display_name, v.first_seen_at,
                   v.comment_count, v.superchat_total
            FROM viewers v
            WHERE v.is_owner = 0 AND v.superchat_total > 0
            ORDER BY v.superchat_total DESC LIMIT ?
        """, (limit,)).fetchall()
    else:
        rows = []
    conn.close()
    return [dict(r) for r in rows]
