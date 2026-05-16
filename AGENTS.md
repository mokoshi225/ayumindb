# AGENTS.md — AyumiDB

あゆみんch 視聴者データベースのアーキテクチャ概要。

## 全体構成

```
ayumindb/
├── ayumindb/          # コアモジュール
│   ├── models.py      # Viewer / Stream / Comment / MembershipEvent のデータクラス
│   ├── db.py          # SQLite CRUD 全操作
│   ├── parser.py      # yt-dlp の live_chat JSON をパース
│   ├── collector.py   # yt-dlp ラッパー（チャット取得）
│   └── app.py         # Streamlit ダッシュボード
├── scripts/
│   ├── export_cookies.py   # Firefox クッキー → cookies.txt
│   ├── export_html.py      # DB → 静的 HTML レポート
│   ├── backfill.py         # 全配信バックフィル
│   └── start_dashboard.bat # Windows 起動用
├── data/
│   ├── ayumindb.db   # SQLite
│   ├── cookies.txt    # Firefox エクスポート（git管理外）
│   ├── dashboard.html # 静的 HTML レポート
│   └── chats/         # .live_chat.json 保管
├── AGENTS.md
├── README.md          # GitHub表示用
├── README.html        # リッチ表示用（GitHub非対応）
└── pyproject.toml
```

## データフロー

```
yt-dlp (live_chat JSON)
        │
        ▼
  parser.py ──→ 視聴者 / コメント / メンバーシップイベント を抽出
        │
        ▼
  db.py ──→ SQLite に保存
        │
        ├── app.py ──→ Streamlit ダッシュボード（http://localhost:8501）
        └── export_html.py ──→ 静的 HTML レポート
```

## スキーマ概要

| テーブル | 主キー | 用途 |
|---|---|---|
| viewers | channel_id | YouTubeチャンネルID 単位の視聴者マスタ |
| streams | video_id | 配信メタデータ |
| comments | (auto) | コメント全文 + 投稿者・種類 |
| membership_events | (auto) | メンバーシップ加入/マイルストーン |
| collection_log | (auto) | 収集状態追跡 |

## 認証

- メン限配信の取得には Firefox クッキーが必要
- `export_cookies.py` で WSL2 上の Windows Firefox から取得
- `cookies.txt` は `.gitignore` で管理外

## レート制限

- yt-dlp の `--sleep-requests 3` で 3秒間隔を強制
- `backfill.py` の `--batch 20` で 20件ごとに長めの休憩
- 1日200件までが安全圏

## 表示

- **Streamlit ダッシュボード** (`app.py`): フルインタラクティブ。視聴者詳細・コメント掘り下げ可
- **静的 HTML** (`export_html.py` → `dashboard.html`): サーバー不要。再生成するまでスナップショット固定
- コメント履歴は 1行「日時: 内容」のコンパクト形式

## メンバーシップ検出

- `liveChatMembershipItemRenderer` → "Member for X months" から加入月を逆算
- `liveChatMemberMilestoneChatRenderer` → マイルストーン
- `liveChatTextMessageRenderer.authorBadges` → 現在のメンバーバッジ
