"""WSL2上のFirefoxからYouTube認証クッキーをNetscape形式でエクスポート"""

import sqlite3
from pathlib import Path

FIREFOX_PROFILES = [
    Path("/mnt/c/Users/mokom/AppData/Roaming/Mozilla/Firefox/Profiles/j82w7skg.default-release/cookies.sqlite"),
    Path("/mnt/c/Users/mokom/AppData/Roaming/Mozilla/Firefox/Profiles/9cdx3u99.default/cookies.sqlite"),
    Path.home() / ".mozilla/firefox" / "*.default-release" / "cookies.sqlite",
]

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "cookies.txt"


def find_cookie_db() -> Path:
    for p in FIREFOX_PROFILES:
        expanded = Path(str(p).replace("*", "*"))  # globは使わず固定
        if p.exists():
            return p
    # WSL2 Linux Firefox
    import glob
    for ptrn in ["~/.mozilla/firefox/*.default-release/cookies.sqlite",
                 "~/.mozilla/firefox/*.default/cookies.sqlite"]:
        matches = list(glob.glob(str(Path(ptrn).expanduser())))
        if matches:
            return Path(matches[0])
    raise FileNotFoundError("Firefox cookies.sqlite not found")


def export_cookies(output_path: Path, cookie_path: Path):
    conn = sqlite3.connect(str(cookie_path))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        cursor = conn.execute("""
            SELECT host, path, isSecure, expiry, name, value
            FROM moz_cookies
            WHERE host LIKE '%.youtube.com'
               OR host LIKE '%.google.com'
               OR host = 'youtube.com'
        """)
        count = 0
        for row in cursor:
            host, path, is_secure, expiry, name, value = row
            if not host.startswith("."):
                host = f".{host}"
            secure_flag = "TRUE" if is_secure else "FALSE"
            f.write(f"{host}\tTRUE\t{path}\t{secure_flag}\t{expiry}\t{name}\t{value}\n")
            count += 1
        print(f"Exported {count} cookies to {output_path}")
    conn.close()


if __name__ == "__main__":
    cookie_db = find_cookie_db()
    print(f"Found cookies: {cookie_db}")
    export_cookies(OUTPUT_PATH, cookie_db)
