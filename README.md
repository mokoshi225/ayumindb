# AyumiDB

あゆみんch ([@ch-uh6rs](https://www.youtube.com/@ch-uh6rs)) の視聴者データベース。
YouTube ライブ配信のチャットを自動収集し、視聴者ごとのコメント履歴、メンバーシップ加入状況、各種ランキングを表示します。

## 機能

- **📡 チャット自動収集** — yt-dlp で過去配信のチャットリプレイを取得
- **👤 視聴者トラッキング** — 初コメント日、コメント数、メンバーシップ状態
- **🔴 メン限対応** — Firefox クッキーで認証、メンバー限定配信もカバー
- **🏆 ランキング** — 古参順、コメント数順、スパチャ額順
- **🔍 コメント全文検索** — 全コメントからのテキスト検索（無制限表示）
- **📈 配信内時系列チャート** — コメント数・発言人數の5分バケット推移
- **📅 全体推移** — 月別コメント数・視聴者数・配信数の長期トレンド
- **🔗 タイムスタンプリンク** — コメント時刻から動画該当箇所に直接ジャンプ
- **📱 2つの表示方法** — Streamlit ダッシュボード + 静的 HTML レポート

## アーキテクチャ

```
yt-dlp (live_chat JSON)
        │
        ▼
  parser.py ──→ 視聴者 / コメント / メンバーシップイベント を抽出
        │
        ▼
  db.py ──→ SQLite に保存
        │
        ├── app.py ──→ Streamlit ダッシュボード（localhost:8501）
        │                  @st.cache_data で高速化
        └── export_html.py ──→ 静的 HTML レポート
```

## セットアップ

### 前提

- WSL2 (Ubuntu) + Python 3.11+
- Windows Firefox（メン限配信取得に必要な場合のみ）

### インストール

```bash
git clone https://github.com/mokoshi225/ayumindb.git
cd ayumindb
pip install -e .
```

### クッキーの準備（メン限配信のみ）

1. Windows Firefox で YouTube にログイン（メンバーシップ加入アカウント）
2. Firefox を閉じる（クッキーDBのロック解除）
3. WSL2 で以下を実行:
   ```bash
   python3 scripts/export_cookies.py
   ```

### データ収集

```bash
# 全配信をバックフィル（初回のみ。完了まで数週間）
python3 scripts/backfill.py --batch 20 --delay 5

# リアルタイム監視（新しい配信を自動検知）
python3 scripts/live_monitor.py
```

### 自動起動設定（WSL2再起動時にバックフィル＋監視が自動開始）

```bash
python3 scripts/setup_autostart.sh
```

### ダッシュボード起動

```bash
# 方法A: Streamlit（インタラクティブ）
streamlit run ayumindb/app.py --server.headless true
# → http://localhost:8501 をブラウザで開く

# 方法B: 静的 HTML（オフライン閲覧用、再生成が必要）
python3 scripts/export_html.py
# → data/dashboard.html を開く
```

## プロジェクト構成

```
ayumindb/
├── ayumindb/               # コアモジュール
│   ├── models.py           # データクラス
│   ├── db.py               # SQLite CRUD + 全文検索
│   ├── parser.py           # チャットJSONパーサー
│   ├── collector.py        # yt-dlp ラッパー
│   └── app.py              # Streamlit ダッシュボード（キャッシュ高速化）
├── scripts/
│   ├── backfill.py         # 一括収集（published_at + stream_started_at対応）
│   ├── live_monitor.py     # リアルタイムライブ監視
│   ├── export_cookies.py   # クッキーエクスポート
│   ├── export_html.py      # HTMLレポート生成
│   ├── start_daemons.sh    # デーモン一括起動
│   ├── setup_autostart.sh  # WSL2自動起動設定
│   └── migrate_stream_started_at.py  # データ移行ツール
├── data/                   # データ保存（git管理外）
├── AGENTS.md
├── README.html
└── README.md
```

## スキーマ

| テーブル | 主キー | 用途 |
|---|---|---|
| viewers | channel_id | 視聴者マスタ |
| streams | video_id | 配信メタデータ（published_at, stream_started_at） |
| comments | (auto) | コメント全文 |
| membership_events | (auto) | メンバーシップ履歴 |
| collection_log | (auto) | 収集状態 |

- `stream_started_at`: 配信の実際の開始時刻（最初のコメントのタイムスタンプから設定）。タイムスタンプリンクの基準。
- `published_at`: yt-dlp の `upload_date` から設定。日付表示用。

## レート制限

- リクエスト間隔: デフォルト 5秒（`--delay` で調整可）
- バッチ休憩: 20件ごとに長めの待機
- 安全圏: 1日200件まで
- yt-dlp の `--sleep-requests 3` で内部でも待機
