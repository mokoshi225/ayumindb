# Failures Log

---

## 2026-05-17: published_at がデータ取得日になってしまう

### 症状
配信一覧で、過去の配信（2021年〜2026年4月）なのに `published_at` が
データ取得日（2026-05-16）になって表示される。59件のストリームが該当。

### 原因
`backfill.py` の `_extract_stream_date()` が `.live_chat.json` の
**1行目**だけを読んで配信日時を推定していた。
しかし1行目は多くの場合 `liveChatViewerEngagementMessageRenderer`
（視聴者エンゲージメントメッセージ = リプレイ取得時にYouTubeが挿入する
システムメッセージ）で、その `timestampUsec` は**リプレイを取得した時刻**
（＝今日）を示していた。
実際のチャットメッセージ（`liveChatTextMessageRenderer`）は2行目以降にある。

また、`datetime.fromtimestamp(ts)` にタイムゾーンを指定していなかったが
これは副次的な問題（システムがJSTなので結果は偶然合っていた）。

### 解決策
1. `_extract_stream_date()` を削除し、代わりに既にパース済みの
   `result["comments"][0].published_at`（`parser.py` が正しくJSTで
   パースした最初のコメント）を使うよう変更。
2. 既存の59件の誤ったデータは `scripts/migrate_published_at.py` で
   `stream_started_at` の日付から訂正。

### 教訓
- `.live_chat.json` の1行目は信頼できない（視聴者エンゲージメントメッセージが入る）
- パース済みのデータ（`parser.py` の出力）を優先して使う
- 生ファイルを読む関数は、ファイル構造の前提が変わると壊れる
- 同じ `timestampUsec` でも `_extract_stream_date`（raw file）と
  `parse_chat_file`（parser.py）で異なる結果になる可能性を考慮する

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

---

## 2026-05-16: backfill.py の datetime 未インポート + 型の不一致

### 症状
tmux で backfill を起動した直後に `NameError: name 'datetime' is not defined` で落ちた。
修正後、次の行で `AttributeError: 'str' object has no attribute 'isoformat'`。

### 原因
1. `backfill()` 関数内で `datetime.strptime()` を使っているのに `from datetime import datetime` がモジュールレベルに無かった（`_extract_stream_date()` 内にしかなかった）
2. `datetime.strptime().isoformat()` と文字列に変換してから `Stream.published_at` に代入していたが、`db.py` の `upsert_stream()` は `.isoformat()` を呼ぶため datetime オブジェクトを期待していた

### 解決策
1. `from datetime import datetime` をモジュールレベルのインポートに追加
2. `datetime.strptime(pub, "%Y%m%d").isoformat()` → `datetime.strptime(pub, "%Y%m%d")` に変更（datetime オブジェクトのまま渡す）

### 教訓
- ヘルパー関数内だけで使っているモジュールを、メイン関数でも使う場合はモジュールレベルに移動する
- データクラスのフィールドに代入する値の型は、そのクラスが何を期待しているかを確認する
- 型ヒントを信頼する（`published_at: Optional[datetime]` なら datetime か None を渡す）

---

## 2026-05-16: time_offset の基準時刻が配信開始時刻ではなく真夜中だった

### 症状
コメント履歴の ▶ リンクをクリックすると動画の先頭（`?t=0`）にしか飛ばない。
または `?t=40000` など巨大な値で全然違う位置に飛ぶ。

### 原因
`time_offset` の計算が `comment_published_at - stream_published_at` だったが、
`stream_published_at` は yt-dlp の `upload_date`（YYYYMMDD、真夜中）を保存していた。
配信は通常 21-23時 JST に始まるため、基準が約21時間ズレていた。
加えて、一部のストリームは published_at が未設定（NULL）のため offset=0 になっていた。

### 解決策
1. `streams` テーブルに `stream_started_at` カラムを新設
2. 最初のコメントの `timestampUsec` を配信開始時刻として保存するよう変更
   （backfill.py + live_monitor.py の両方）
3. `time_offset` の計算基準を `COALESCE(s.stream_started_at, s.published_at)` に変更
4. 既存85ストリームの `stream_started_at` をマイグレーションでバックフィル
5. `init_db()` に ALTER TABLE マイグレーションを追加して既存DBと互換性を維持

### 教訓
- 配信の「日付」と「実際の開始時刻」は別物。`upload_date` は日付のみで時刻情報がない
- ライブ配信の開始時刻を知るには、最初のチャットメッセージのタイムスタンプを使うのが確実
- スキーマ変更が必要な場合は `init_db()` に ALTER TABLE + try/except パターンで対応する
- テーブル定義だけでなく、データクラス（models.py）と Row→オブジェクト変換（`_row_to_stream`）も同時に更新する

---

## 2026-05-16: Streamlit が全視聴者を毎回再クエリ + 6000個のボタンを再描画

### 症状
ランキング切り替え・並び替え・フィルター変更時にブラウザが約5秒フリーズする。

### 原因
Streamlit はユーザー操作のたびにスクリプト全体を再実行する。
そのたびに以下が走っていた:
1. `get_all_viewers()`: 6074行の視聴者データを相関サブクエリ付きでSQL再実行（**1163ms**）
2. `show_viewers()`: 6074個の `st.button()` を生成してグリッド表示（ウィジェット数過多）

### 解決策
1. **`@st.cache_data(ttl=60)` 導入**: データフェッチ関数にキャッシュを追加。60秒間は再クエリしない
   - `_cached_viewers()`, `_cached_rankings()`, `_cached_stats()` の3関数
2. **`st.dataframe` に置き換え**: 6074個の `st.button()` を1個の `st.dataframe` + 視聴者選択用 `st.selectbox` に変更
   - フィルター・ソートは Python 上でキャッシュ済みデータに対して行う（ミリ秒）

### 教訓
- Streamlit は stateless なスクリプト再実行モデル。高コストな処理は `@st.cache_data` で明示的にキャッシュする
- 大量のウィジェット（数千のボタン）はフレームレートを著しく低下させる
- 一覧表示は `st.dataframe`、選択操作は `st.selectbox` が適切
- フィルター・ソートはSQLでやるよりPythonでやったほうがキャッシュ効率が良い

---

## 2026-05-16: SQLite strftime の %s が %%s と書かれていて常に0を返していた

### 症状
コメントのタイムリンク（▶）が常に動画の最初にしか飛ばない。
`time_offset` が常に0。

### 原因
`db.py` の `strftime` 呼び出しで、フォーマット文字列が `'%%s'` と書かれていた。
Python では文字列中の `%%` は特別なエスケープではない（`%` フォーマットや f-string でのみ有効）。
そのため SQLite には `strftime('%%s', ...)` がそのまま渡された。
SQLite の `strftime` では `%%` は「リテラルの %」を意味するため、`%%s` → 文字列 `%s` を返す。
`CAST('%s' AS INTEGER)` = 0 となり、offset は常に0になっていた。

### 解決策
`strftime('%%s', ...)` → `strftime('%s', ...)` に修正（4箇所）。

### 教訓
- Python の `%%` エスケープは `%` 演算子と f-string でのみ機能する。通常の文字列リテラルでは `%%` はそのまま `%%`
- SQLite の strftime に渡すフォーマットはシングルクォート内の `%s`（パーセント1つ）で正しい
- バグが最初から存在していたが、「リンクが動画先頭に飛ぶ」という挙動が自然に見えていたため長期間気づかれなかった
- 原因を特定するには、get_conn() 経由と raw sqlite3 接続の結果を比較するのが有効

---

## 2026-05-17: None の published_at で strftime を呼んで AttributeError

### 症状
配信一覧タブを開くと `AttributeError: 'NoneType' object has no attribute 'strftime'` が発生。
`app.py` の `show_streams()` 内で `s.published_at.strftime(...)` の行が指摘された。

### 原因
一部のストリーム（古いデータや収集中のもの）は `published_at` が `NULL`（None）だが、
配信分析用セレクトボックスの選択肢リストを生成する際に、
`f"{s.published_at.strftime(...)} {s.title[:60]}"` と何のガードもなく
`.strftime()` を呼んでいた。`published_at` が None のストリームで必ず落ちる。

### 解決策
```python
# Before:
f"{s.published_at.strftime('%Y-%m-%d')} {s.title[:60]}"
for s in streams

# After:
f"{s.published_at.strftime('%Y-%m-%d')} {s.title[:60]}"
if s.published_at else s.title[:60]
for s in streams
```
同じファイル内の他の `strftime` 呼び出しを全部確認し、すでにガードされているものだけが残っていることを確認した。

### 教訓
- データクラスの `Optional[datetime]` フィールドに対して `.strftime()` を呼ぶときは**常に** `if ... else` でガードする
- エラーが出た1行だけ直すのではなく、 grep で同パターンを全量確認する
- st.dataframe に移行する際に、古い markdown レンダリングでは暗黙に回避されていた None 問題が表面化することがある
