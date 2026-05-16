# Failures Log

このセッションで起きた失敗とその解決策を記録する。
新しい失敗を見つけたら追記すること。

---

## 2026-05-16: 相対インポートエラー

### 症状
`streamlit run ayumindb/app.py` で `ImportError: attempted relative import with no known parent package`

### 原因
`app.py` が `from .db import ...` という相対インポートを使っていたが、
Streamlit がモジュールとしてではなく script として直接実行するため、
パッケージ階層が認識されなかった。

### 解決策
相対インポートをやめ、`sys.path.insert(0, ...)` でプロジェクトルートを
パスに追加した上で `from ayumindb.db import ...` と絶対インポートに変更した。

### 教訓
- エントリポイントになるファイル（`app.py` 等）では相対インポートを使わない
- `streamlit run` で起動するファイルはスクリプトとして実行されることを前提にする

---

## 2026-05-16: SQLite FOREIGN KEY 制約違反

### 症状
`sqlite3.IntegrityError: FOREIGN KEY constraint failed` がコメント挿入時に発生

### 原因
comments テーブルが viewers と streams に外部キー参照しているが、
コメントを先に挿入しようとして参照先のレコードが存在しなかった。

### 解決策
挿入順序を `streams → viewers → comments → membership_events` に変更した。

### 教訓
- FK制約があるテーブルへの挿入は、参照される側 → 参照する側 の順序を守る
- `upsert_stream` を `insert_comments_batch` より前に呼ぶ

---

## 2026-05-16: Stream データクラスに collection_status が欠如

### 症状
backfill.py 実行時に `AttributeError: 'Stream' object has no attribute 'collection_status'`

### 原因
`models.py` の `Stream` データクラスに `collection_status` フィールドがなかった。
DBにはカラムがあるのに、`_row_to_stream()` がマッピングできない状態だった。

### 解決策
`models.py` の `Stream` に `collection_status: str = "pending"` を追加。
同時に `db.py` の `_row_to_stream()` にもフィールドを追加。

### 教訓
- データクラスとDBスキーマの整合性を常に確認する
- 新しいカラムをDBに追加したらモデル定義も更新する

---

## 2026-05-16: --cookies フラグが yt-dlp の前に置かれた

### 症状
`FileNotFoundError: [Errno 2] No such file or directory: '--cookies'`
サブプロセスが `--cookies` を実行可能ファイルとして探そうとした。

### 原因
`cmd = ["--cookies", str(COOKIE_FILE)] + cmd` とリスト結合した結果、
`["--cookies", "path/to/cookies.txt", "yt-dlp", ...]` となり、
OSが最初の要素 `--cookies` をコマンドとして実行しようとした。

### 解決策
`cmd[1:1] = ["--cookies", str(COOKIE_FILE)]` として、
`yt-dlp` の直後にオプションを挿入する方式に統一した。
また、全関数で同じバグを繰り返さないよう `_with_cookies()` ヘルパー関数を導入した。

### 教訓
- `subprocess.run(cmd)` では cmd[0] が実行ファイル名になる
- リスト結合 `[a] + cmd` は cmd[0] を先頭にしないよう注意
- 共通処理はヘルパー関数に抽出してバグの拡散を防ぐ

---

## 2026-05-16: nohup バックグラウンドジョブがbashツールのタイムアウトで死ぬ

### 症状
バックフィルが2件処理したところで止まった。
プロセスが存在せず、エラーログもなかった。

### 原因
`nohup ... &` で起動したプロセスが、bash ツールのタイムアウト（120秒）で
プロセスグループごと強制終了された。

### 解決策
`tmux` セッション内でプロセスを実行し、bash ツールのライフサイクルから切り離した。
`tmux new-session -d -s ayumindb 'command'`

### 教訓
- 長時間バックグラウンドジョブは `nohup` だけでは不十分
- bash ツールのタイムアウトはプロセスグループ全体にシグナルを送る
- `tmux` または `screen` を使うのが確実

---

## 2026-05-16: SQLite スパチャ金額カンマ問題

### 症状
スパチャ ¥15,800 が ¥15 と表示される。¥5,000 が ¥5 と表示される。

### 原因
`CAST(REPLACE(super_chat_amount_text, '¥', '') AS INTEGER)` としていたが、
金額は `¥15,800` のようにカンマ区切り。
`REPLACE` で `¥` を消した後の `15,800` を `CAST` すると、
SQLite はカンマ以降を無視して `15` として扱う。

### 解決策
`REPLACE` を2重にしてカンマも除去:
```sql
CAST(REPLACE(REPLACE(super_chat_amount_text, '¥', ''), ',', '') AS INTEGER)
```

### 教訓
- SQLite の `CAST` はカンマ区切り数値を正しくパースしない
- 金額のパースでは記号と区切り文字を両方除去してからキャストする
- `grep` で同じパターンがほかにないか確認する（3箇所あった）

---

## 2026-05-16: 配信日時がDBに保存されていなかった

### 症状
コメント履歴のタイムスタンプリンクが `?t=0`（先頭）にしか飛ばない。
コメントと配信の時間差が計算できない。

### 原因
`backfill.py` が `Stream` を `upsert` する際に `published_at` を
設定していなかった。ストリーム一覧（flat-playlist）には日時情報がない。

### 解決策
`collector.py` に `get_video_info()` 関数を追加し、各配信のメタデータから
`upload_date` を取得して `published_at` に設定するようにした。

### 教訓
- 配信メタデータは `--dump-json` で個別に取得する必要がある
- 一度DBに入れたデータの修正は後から大変なので、最初から正しく保存する
- 既存レコードのバッチ修正用ワンオフスクリプトも用意しておく
