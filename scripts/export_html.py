"""SQLiteのデータから静的なHTMLレポートを生成（Windowsから直接開ける）"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb import VERSION, GITHUB_URL
from ayumindb.db import init_db, get_stats, get_rankings, get_all_viewers, get_all_streams, recompute_viewer_stats

OUTPUT = Path(__file__).parent.parent / "data" / "dashboard.html"


def build_html():
    init_db()
    recompute_viewer_stats()
    stats = get_stats()

    oldest = get_rankings("oldest", 50)
    comments_rank = get_rankings("comments", 50)
    superchat_rank = get_rankings("superchat", 50)
    viewers = get_all_viewers()
    streams = get_all_streams()

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AyumiDB - あゆみんch 視聴者データベース</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f0f0f; color: #eee; padding: 20px; }}
  h1 {{ color: #f00; margin-bottom: 20px; }}
  h2 {{ color: #fff; margin: 24px 0 12px; border-bottom: 2px solid #333; padding-bottom: 4px; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }}
  .stat-card {{ background: #1a1a1a; padding: 16px; border-radius: 8px; text-align: center; }}
  .stat-card .value {{ font-size: 28px; font-weight: bold; color: #fff; }}
  .stat-card .label {{ font-size: 12px; color: #888; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
  th {{ background: #1a1a1a; color: #aaa; text-align: left; padding: 8px 10px; cursor: pointer; position: sticky; top: 0; }}
  th:hover {{ color: #fff; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #222; }}
  tr:hover {{ background: #1a1a1a; }}
  .member-badge {{ color: #ff4444; font-weight: bold; }}
  .tab {{ display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }}
  .tab button {{ background: #222; color: #aaa; border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer; }}
  .tab button.active {{ background: #f00; color: #fff; }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .rank-num {{ display: inline-block; width: 28px; text-align: center; font-weight: bold; }}
  .rank-1 {{ color: gold; }} .rank-2 {{ color: silver; }} .rank-3 {{ color: #cd7f32; }}
  a {{ color: #4af; text-decoration: none; }}
  input[type=text] {{ background: #222; border: 1px solid #444; color: #eee; padding: 8px 12px; border-radius: 4px; width: 100%; max-width: 300px; margin-bottom: 12px; }}
  @media (prefers-color-scheme: light) {{
    body {{ background: #fff; color: #222; }}
    h2 {{ color: #000; border-bottom-color: #ddd; }}
    .stat-card {{ background: #f5f5f5; }}
    .stat-card .value {{ color: #000; }}
    td {{ border-bottom-color: #eee; }}
    tr:hover {{ background: #f9f9f9; }}
    th {{ background: #eee; color: #666; }}
    .tab button {{ background: #ddd; color: #666; }}
    .tab button.active {{ background: #f00; color: #fff; }}
    input[type=text] {{ background: #fff; border-color: #ccc; color: #000; }}
  }}
</style>
</head>
<body>
<h1>📊 あゆみんch 視聴者データベース</h1>

<div class="stats">
  <div class="stat-card"><div class="value">{stats.get('viewer_count',0)}</div><div class="label">総視聴者数</div></div>
  <div class="stat-card"><div class="value">{stats.get('member_count',0)}</div><div class="label">メンバー数</div></div>
  <div class="stat-card"><div class="value">{stats.get('stream_count',0)}</div><div class="label">記録配信数</div></div>
  <div class="stat-card"><div class="value">{stats.get('comment_count',0)}</div><div class="label">総コメント数</div></div>
  <div class="stat-card"><div class="value">{stats.get('superchat_count',0)}</div><div class="label">スパチャ数</div></div>
</div>

<div class="tab">
  <button class="active" onclick="switchTab('oldest')">🏆 古参ランキング</button>
  <button onclick="switchTab('comments')">💬 コメント数ランキング</button>
  <button onclick="switchTab('superchat')">💰 スパチャランキング</button>
  <button onclick="switchTab('viewers')">👤 視聴者一覧</button>
  <button onclick="switchTab('streams')">📹 配信一覧</button>
</div>
"""

    # --- 古参ランキング ---
    html += '<div id="tab-oldest" class="tab-content active">\n<h2>🏆 古参ランキング</h2>\n'
    html += '<input type="text" id="filter-oldest" placeholder="名前で検索..." oninput="filterTable(\'oldest\')">\n'
    html += '<table id="table-oldest"><thead><tr><th>順位</th><th onclick="sortTable(\'oldest\',1)">名前</th><th onclick="sortTable(\'oldest\',2)">初コメント</th><th onclick="sortTable(\'oldest\',3)">コメント数</th></tr></thead><tbody>\n'
    for i, r in enumerate(oldest, 1):
        cls = f'rank-{i}' if i <= 3 else ''
        name = r.get('display_name', '?')
        first = r.get('first_seen_at', '?')[:10] if r.get('first_seen_at') else '?'
        cc = r.get('comment_count', 0)
        html += f'<tr><td><span class="rank-num {cls}">{i}</span></td><td>{name}</td><td>{first}</td><td>{cc}</td></tr>\n'
    html += '</tbody></table></div>\n'

    # --- コメント数ランキング ---
    html += '<div id="tab-comments" class="tab-content">\n<h2>💬 コメント数ランキング</h2>\n'
    html += '<input type="text" id="filter-comments" placeholder="名前で検索..." oninput="filterTable(\'comments\')">\n'
    html += '<table id="table-comments"><thead><tr><th>順位</th><th onclick="sortTable(\'comments\',1)">名前</th><th onclick="sortTable(\'comments\',2)">コメント数</th></tr></thead><tbody>\n'
    for i, r in enumerate(comments_rank, 1):
        cls = f'rank-{i}' if i <= 3 else ''
        name = r.get('display_name', '?')
        cc = r.get('comment_count', 0)
        html += f'<tr><td><span class="rank-num {cls}">{i}</span></td><td>{name}</td><td>{cc}</td></tr>\n'
    html += '</tbody></table></div>\n'

    # --- スパチャランキング ---
    html += '<div id="tab-superchat" class="tab-content">\n<h2>💰 スパチャランキング</h2>\n'
    html += '<input type="text" id="filter-superchat" placeholder="名前で検索..." oninput="filterTable(\'superchat\')">\n'
    html += '<table id="table-superchat"><thead><tr><th>順位</th><th onclick="sortTable(\'superchat\',1)">名前</th><th onclick="sortTable(\'superchat\',2)">総額</th><th onclick="sortTable(\'superchat\',3)">スパチャ数</th></tr></thead><tbody>\n'
    for i, r in enumerate(superchat_rank, 1):
        cls = f'rank-{i}' if i <= 3 else ''
        name = r.get('display_name', '?')
        total = r.get('superchat_total', 0) or 0
        cc = r.get('comment_count', 0)
        html += f'<tr><td><span class="rank-num {cls}">{i}</span></td><td>{name}</td><td>¥{int(total):,}</td><td>{cc}</td></tr>\n'
    html += '</tbody></table></div>\n'

    # --- 視聴者一覧 ---
    html += '<div id="tab-viewers" class="tab-content">\n<h2>👤 視聴者一覧</h2>\n'
    html += '<input type="text" id="filter-viewers" placeholder="名前で検索..." oninput="filterTable(\'viewers\')">\n'
    html += '<table id="table-viewers"><thead><tr><th onclick="sortTable(\'viewers\',0)">名前</th><th onclick="sortTable(\'viewers\',1)">初コメント</th><th onclick="sortTable(\'viewers\',2)">メンバー</th><th onclick="sortTable(\'viewers\',3)">コメント数</th><th onclick="sortTable(\'viewers\',4)">スパチャ額</th></tr></thead><tbody>\n'
    for v in viewers:
        name = v.display_name
        first = v.first_seen_at.strftime('%Y-%m-%d') if v.first_seen_at else '?'
        mem = '<span class="member-badge">✅</span>' if v.is_member else ''
        cc = v.comment_count
        sc = f'¥{v.superchat_total:,}' if v.superchat_total > 0 else ''
        html += f'<tr><td>{name}</td><td>{first}</td><td>{mem}</td><td>{cc}</td><td>{sc}</td></tr>\n'
    html += '</tbody></table></div>\n'

    # --- 配信一覧 ---
    html += '<div id="tab-streams" class="tab-content">\n<h2>📹 配信一覧</h2>\n'
    html += '<input type="text" id="filter-streams" placeholder="タイトルで検索..." oninput="filterTable(\'streams\')">\n'
    html += '<input type="text" id="filter-streams" placeholder="タイトルで検索..." oninput="filterTable(\'streams\')">\n'
    html += '<table id="table-streams"><thead><tr><th onclick="sortTable(\'streams\',0)">タイトル</th><th onclick="sortTable(\'streams\',1)">日時</th><th onclick="sortTable(\'streams\',2)">時間</th><th onclick="sortTable(\'streams\',3)">コメント数</th><th onclick="sortTable(\'streams\',4)">視聴者数</th><th>リンク</th><th>メン限</th></tr></thead><tbody>\n'
    for s in streams:
        title = s.title[:60]
        date = s.published_at.strftime('%Y-%m-%d') if s.published_at else '?'
        dur = f'{s.duration_sec // 3600}h{(s.duration_sec % 3600) // 60:02d}m' if s.duration_sec else '?'
        cc = s.chat_count
        uv = s.unique_viewers
        link = f'<a href="https://youtu.be/{s.video_id}" target="_blank">▶</a>'
        mem = '🔒' if s.is_member_only else ''
        html += f'<tr><td>{title}</td><td>{date}</td><td>{dur}</td><td>{cc}</td><td>{uv}</td><td>{link}</td><td>{mem}</td></tr>\n'
    html += '</tbody></table></div>\n'

    # JavaScript
    html += """
<script>
function switchTab(name) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelector('.tab button:nth-child(' + ({oldest:1,comments:2,superchat:3,viewers:4,streams:5}[name] || 1) + ')').classList.add('active');
}

function filterTable(tab) {
  const input = document.getElementById('filter-' + tab);
  const filter = input.value.toLowerCase();
  const table = document.getElementById('table-' + tab);
  const rows = table.getElementsByTagName('tr');
  for (let i = 1; i < rows.length; i++) {
    const text = rows[i].textContent.toLowerCase();
    rows[i].style.display = text.includes(filter) ? '' : 'none';
  }
}

function sortTable(tab, col) {
  const table = document.getElementById('table-' + tab);
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const ascending = table.dataset.sortCol == col ? table.dataset.sortAsc !== 'true' : true;
  table.dataset.sortCol = col;
  table.dataset.sortAsc = ascending;
  rows.sort((a, b) => {
    let va = a.cells[col]?.textContent.trim() || '';
    let vb = b.cells[col]?.textContent.trim() || '';
    const na = parseFloat(va.replace(/[^0-9.-]/g, ''));
    const nb = parseFloat(vb.replace(/[^0-9.-]/g, ''));
    if (!isNaN(na) && !isNaN(nb)) { va = na; vb = nb; }
    if (va < vb) return ascending ? -1 : 1;
    if (va > vb) return ascending ? 1 : -1;
    return 0;
  });
  rows.forEach(r => tbody.appendChild(r));
}
</script>
<footer style="text-align:center;color:#666;font-size:12px;margin-top:40px;padding:20px 0;border-top:1px solid #333;">
  AyumiDB v{VERSION} | <a href="{GITHUB_URL}" style="color:#4af;">GitHub</a>
</footer>
</body>
</html>
"""

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build_html()
    print(f"✅ Static HTML generated: {path}")
    print(f"   Windows から開く: \\\\wsl.localhost\\opencode\\home\\mokoshi\\ayumindb\\data\\dashboard.html")
