"""yt-dlp を使ったチャット取得"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import yt_dlp

from .models import Stream

DATA_DIR = Path(__file__).parent.parent / "data"
COOKIE_FILE = DATA_DIR / "cookies.txt"
CHAT_DIR = DATA_DIR / "chats"


def get_channel_streams(channel_url: str = "https://www.youtube.com/@ch-uh6rs/streams") -> list[dict]:
    """チャンネルの全配信メタデータを取得"""
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "force_json": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    if info and "entries" in info:
        return [
            {
                "id": e["id"],
                "title": e.get("title", ""),
                "duration": e.get("duration", 0),
                "url": e.get("webpage_url", f"https://www.youtube.com/watch?v={e['id']}"),
            }
            for e in info["entries"]
            if e
        ]
    return []


def stream_has_chat(video_id: str, use_cookies: bool = False) -> bool:
    """当該配信にチャットリプレイが存在するか確認"""
    cmd = [
        "yt-dlp", "--write-subs", "--sub-langs", "live_chat",
        "--skip-download", "--ignore-no-formats-error",
        "--sleep-requests", "2",
        "-o", str(CHAT_DIR / "%(id)s"),
    ]
    if use_cookies and COOKIE_FILE.exists():
        cmd = ["--cookies", str(COOKIE_FILE)] + cmd
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if "Writing video subtitles to" in result.stdout or "Writing video subtitles to" in result.stderr:
        return True
    if "join this channel" in result.stderr.lower() or "members-only" in result.stderr.lower():
        return False  # 認証不足
    return False


def download_chat(video_id: str, use_cookies: bool = False) -> Optional[Path]:
    """チャットJSONをダウンロードしてパスを返す"""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    output = CHAT_DIR / f"{video_id}.live_chat.json"
    if output.exists():
        return output

    cmd = [
        "yt-dlp", "--write-subs", "--sub-langs", "live_chat",
        "--skip-download", "--ignore-no-formats-error",
        "--sleep-requests", "3",
        "-o", str(CHAT_DIR / "%(id)s"),
    ]
    if use_cookies and COOKIE_FILE.exists():
        cmd = ["--cookies", str(COOKIE_FILE)] + cmd
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        pass

    return output if output.exists() else None
