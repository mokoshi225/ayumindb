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
STREAM_CACHE = DATA_DIR / "streams_cache.json"


def _with_cookies(cmd: list[str], use_cookies: bool) -> list[str]:
    if use_cookies and COOKIE_FILE.exists():
        cmd[1:1] = ["--cookies", str(COOKIE_FILE)]
    return cmd


def get_channel_streams(channel_url: str = "https://www.youtube.com/@ch-uh6rs/streams") -> list[dict]:
    if STREAM_CACHE.exists():
        age = datetime.now().timestamp() - STREAM_CACHE.stat().st_mtime
        if age < 86400:
            with open(STREAM_CACHE) as f:
                return json.load(f)

    ydl_opts = {"quiet": True, "extract_flat": True, "force_json": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
        if info and "entries" in info:
            result = [
                {
                    "id": e["id"],
                    "title": e.get("title", ""),
                    "duration": e.get("duration", 0),
                    "url": e.get("webpage_url", f"https://www.youtube.com/watch?v={e['id']}"),
                }
                for e in info["entries"]
                if e
            ]
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(STREAM_CACHE, "w") as f:
                json.dump(result, f, ensure_ascii=False)
            return result
    except Exception as e:
        if STREAM_CACHE.exists():
            with open(STREAM_CACHE) as f:
                return json.load(f)
        raise e
    return []


def _run_ytdlp(video_id: str, use_cookies: bool, sleep: str = "3", timeout: int = 600) -> Optional[Path]:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    output = CHAT_DIR / f"{video_id}.live_chat.json"
    if output.exists():
        return output

    cmd = _with_cookies([
        "yt-dlp", "--write-subs", "--sub-langs", "live_chat",
        "--skip-download", "--ignore-no-formats-error",
        "--sleep-requests", sleep,
        "-o", str(CHAT_DIR / "%(id)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ], use_cookies)
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    return output if output.exists() else None


def stream_has_chat(video_id: str, use_cookies: bool = False) -> bool:
    result = subprocess.run(
        _with_cookies([
            "yt-dlp", "--write-subs", "--sub-langs", "live_chat",
            "--skip-download", "--ignore-no-formats-error",
            "--sleep-requests", "2",
            "-o", str(CHAT_DIR / "%(id)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ], use_cookies),
        capture_output=True, text=True, timeout=300,
    )
    out = result.stdout + result.stderr
    if "Writing video subtitles to" in out:
        return True
    if "join this channel" in out.lower() or "members-only" in out.lower():
        return False
    return False


def download_chat(video_id: str, use_cookies: bool = False) -> Optional[Path]:
    return _run_ytdlp(video_id, use_cookies, sleep="3", timeout=600)


def check_live() -> list[dict]:
    cmd = [
        "yt-dlp", "--dump-json", "--flat-playlist",
        "--ignore-no-formats-error",
        "--sleep-requests", "1",
        "https://www.youtube.com/@ch-uh6rs/live",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        streams = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                streams.append({
                    "id": d["id"],
                    "title": d.get("title", ""),
                    "url": d.get("webpage_url", f"https://www.youtube.com/watch?v={d['id']}"),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return streams
    except (subprocess.TimeoutExpired, Exception):
        return []


def start_live_capture(video_id: str, use_cookies: bool = False) -> subprocess.Popen:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = _with_cookies([
        "yt-dlp", "--write-subs", "--sub-langs", "live_chat",
        "--skip-download", "--ignore-no-formats-error",
        "--sleep-requests", "1",
        "-o", str(CHAT_DIR / "%(id)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ], use_cookies)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
