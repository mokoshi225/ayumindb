# AGENTS.md — AyumiDB

あゆみんch 視聴者データベースのアーキテクチャ概要。

## セッションを跨ぐ永続指示

1. **作業開始前に `failures.md` を読むこと。** 過去の失敗と解決策が記録されている。同じ失敗を繰り返してはならない。
2. **新しい失敗に遭遇したら `failures.md` に追記すること。** 症状・原因・解決策・教訓を必ず書く。成功したらその直後に記録する。
3. **`AGENTS.md` 自体も必要に応じて更新すること。** アーキテクチャの変更、新しいスクリプトの追加、設定値の変更はここに反映する。
4. **バージョンは `ayumindb/__init__.py` の VERSION を更新すること。** コード修正のたびにインクリメントする。
5. **ブランチ運用（改定）**:
   - **`main` を直接編集しない。** `main` はマージ専用の安定ブランチ。
   - **作業フロー**: `main` から feature branch を作成 → 作業完了 → `main` にマージ → branch 削除。
   - **分岐条件（いずれかに該当したら必ず branch を作成）**:
     - 2ファイル以上の変更
     - ロジックの追加・変更
     - DBスキーマの変更
     - 設定値の変更（`__init__.py` のバージョン更新を除く）
   - **例外（main直編集可）**: 1ファイルのタイポ修正のみ。
   - **branch名**: `feature/<簡潔な説明>` または `fix/<簡潔な説明>`。
   - **セッション開始時の確認**: 作業前に `git branch` で現在のブランチと変更状態を確認する。`main` にいる場合は分岐条件に照らして branch が必要か判断する。

## 全体構成

```
ayumindb/
├── ayumindb/          # コアモジュール
│   ├── models.py      # Viewer / Stream / Comment / MembershipEvent のデータクラス
│   ├── db.py          # SQLite CRUD 全操作 + 全文検索 + stream_started_at 対応
│   │                  # + get_stream_time_series() / get_overall_time_series()
│   ├── parser.py      # yt-dlp の live_chat JSON をパース
│   ├── collector.py   # yt-dlp ラッパー（チャット取得）
│   └── app.py         # Streamlit ダッシュボード（@st.cache_data + Plotly チャート）
├── scripts/
│   ├── backfill.py         # 全配信バックフィル（stream_started_at 保存対応）
│   ├── live_monitor.py     # リアルタイムライブ監視（stream_started_at 保存対応）
│   ├── export_cookies.py   # Firefox クッキー → cookies.txt
│   ├── export_html.py      # DB → 静的 HTML レポート
│   ├── start_daemons.sh    # tmux 経由で backfill + monitor を一括起動
│   ├── setup_autostart.sh  # .bashrc に自動起動設定を追記
│   ├── migrate_stream_started_at.py  # 既存ストリームの stream_started_at 移行ツール
│   ├── migrate_published_at.py       # 誤った published_at を stream_started_at から訂正
├── data/
│   ├── ayumindb.db   # SQLite
│   ├── cookies.txt    # Firefox エクスポート（git管理外）
│   ├── dashboard.html # 静的 HTML レポート
│   ├── chats/         # .live_chat.json 保管
│   ├── streams_cache.json  # 配信一覧キャッシュ（24h TTL）
│   ├── backfill.log   # バックフィル実行ログ
│   └── monitor.log    # ライブモニター実行ログ
├── AGENTS.md
├── README.md          # GitHub表示用
├── README.html        # リッチ表示用（GitHub非対応）
├── failures.md        # 失敗・解決策の記録
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

- `streams.stream_started_at`: 配信の実際の開始時刻。最初のコメントの `timestampUsec` から設定。
- `viewers.comment_count` / `viewers.superchat_total`: 実体化された集計値。コメント挿入時にインクリメント更新され、`recompute_viewer_stats()` で整合性を確保。

## データフロー（詳細）

```
yt-dlp (live_chat JSON)
        │
        ▼
  parser.py ──→ 視聴者 / コメント / メンバーシップイベント を抽出
        │             コメントの published_at は JST (+09:00) で保存
        ▼
  db.py ──→ SQLite に保存
        │     - time_offset = comment_time - stream_started_at
        │     - stream_started_at は最初のコメントのタイムスタンプ
        │     - コメントの ▶ リンク: youtu.be/{video_id}?t={time_offset}
        │     - viewer.comment_count / superchat_total はコメント挿入時に
        │       インクリメント更新（実体化カラム）。サブクエリ不要。
        │     - backfill.py 完了時 / export_html.py 実行時に
        │       recompute_viewer_stats() で整合性を確保
        │
        ├── app.py ──→ Streamlit ダッシュボード（http://localhost:8501）
        │                  @st.cache_data(ttl=60) でクエリ結果をキャッシュ
        │                  視聴者一覧は st.dataframe + st.selectbox で軽量表示
        │                  Plotly 時系列チャート（配信内・全体推移）
        │
        └── export_html.py ──→ 静的 HTML レポート
```

## パフォーマンス設計

- **Streamlit キャッシュ**: `_cached_viewers()`, `_cached_rankings()`, `_cached_stats()` に `@st.cache_data(ttl=60)` を適用。60秒間はSQL再実行しない。時系列データも `_cached_stream_time_series()`, `_cached_overall_time_series()` で同様にキャッシュ。
- **一覧表示**: 視聴者一覧・配信一覧は `st.dataframe()` + 選択用 `st.selectbox()` で表示。フィルター・ソートはPython上でキャッシュ済みデータに対して実行。列クリックソート対応。
- **ストリーム開始時刻**: `stream_started_at` を最初のコメントから取得。SQLite strftime で時刻差（秒）を計算。
- **時系列チャート**: Plotly（px.bar / px.line）5分バケットの配信内分析と月別の全体推移。`st.plotly_chart(use_container_width=True)` でレスポンシブ表示。

## ライブ監視

- `scripts/live_monitor.py` が 5分おきにチャンネルのライブ配信をチェック
- 新規配信を検知すると yt-dlp でチャットをリアルタイム追撃開始
- 配信終了後、チャットリプレイがあればフル取得で補完
- 検知から最長5分のラグがあるが、配信開始からの全コメントをカバー

## 認証

- メン限配信の取得には Firefox クッキーが必要
- `export_cookies.py` で WSL2 上の Windows Firefox から取得
- `cookies.txt` は `.gitignore` で管理外

## レート制限

- yt-dlp の `--sleep-requests 3` で 3秒間隔を強制
- `backfill.py` の `--batch 20` で 20件ごとに長めの休憩
- 1日200件までが安全圏

## 表示

- **Streamlit ダッシュボード** (`app.py`): フルインタラクティブ。視聴者詳細・コメント掘り下げ可、コメント全文検索、タイムスタンプリンク
- **静的 HTML** (`export_html.py` → `dashboard.html`): サーバー不要。再生成するまでスナップショット固定
- コメント履歴は 1行「日時: 内容」のコンパクト形式
- ▶ リンクで動画該当箇所に直接ジャンプ（`?t={time_offset_sec}`）
- **配信一覧**: `st.dataframe()` 全カラムクリックソート対応（日時/タイトル/時間/コメント数/視聴者数/コメ/h/人/h）
- **配信分析**: 配信選択式の Plotly 時系列チャート（コメント数・発言人數、5分バケット）
- **全体推移**: 月別のコメント数・ユニーク視聴者数・配信数を Plotly で表示

## メンバーシップ検出

- `liveChatMembershipItemRenderer` → "Member for X months" から加入月を逆算
- `liveChatMemberMilestoneChatRenderer` → マイルストーン
- `liveChatTextMessageRenderer.authorBadges` → 現在のメンバーバッジ

## WSL2 自動起動

- `.bashrc` に `bash ~/ayumindb/scripts/start_daemons.sh` が登録されている
- WSL2 起動時に tmux セッション `ayumindb`（backfill）と `monitor`（live_monitor）が自動開始
- `scripts/setup_autostart.sh` で設定可能

## 既知の注意点

- **`strftime('%s')` のフォーマット**: SQLite の strftime に渡すフォーマット文字列は `'%s'`（パーセント1つ）が正しい。`'%%s'` だとリテラルの `%s` が返る（`%%` は SQLite でリテラル%を意味する）。
- **コメント時刻のタイムゾーン**: `parser.py` はコメント時刻を JST (+09:00) 付きで保存する。SQLite 3.45+ の strftime はタイムゾーンオフセットを正しく解釈する。
