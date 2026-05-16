import streamlit as st
import pandas as pd
from datetime import datetime
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb import VERSION, GITHUB_URL
from ayumindb.db import (
    init_db, get_all_viewers, get_viewer, get_all_streams, get_stream,
    get_comments_by_viewer, get_comments_by_stream, get_membership_events_by_viewer,
    search_comments, get_stats, get_rankings,
)

st.set_page_config(page_title="AyumiDB", layout="wide", page_icon="📊")

# ---- Cached data fetchers (B-1: avoid re-query on every interaction) ----

@st.cache_data(ttl=60)
def _cached_viewers():
    return get_all_viewers()

@st.cache_data(ttl=60)
def _cached_rankings(rank_type: str, limit: int):
    return get_rankings(rank_type, limit)

@st.cache_data(ttl=60)
def _cached_stats():
    return get_stats()


def yt_link(video_id: str, t: int = 0) -> str:
    if t > 0:
        return f"https://youtu.be/{video_id}?t={t}"
    return f"https://youtu.be/{video_id}"


def yt_markdown(video_id: str, label: str = "", t: int = 0) -> str:
    url = yt_link(video_id, t)
    text = label or video_id
    return f'<a href="{url}" target="_blank">{text}</a>'


def main():
    init_db()
    st.title("📊 あゆみんch 視聴者データベース")

    # 検索を最上部に
    search_query = st.text_input("🔍 コメント全文検索", placeholder="コメント内容を入力...")
    if search_query:
        show_search_results(search_query)
        st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["ダッシュボード", "視聴者一覧", "ランキング", "配信一覧"])

    with tab1:
        show_dashboard()
    with tab2:
        show_viewers()
    with tab3:
        show_rankings()
    with tab4:
        show_streams()


def show_search_results(query: str):
    results = search_comments(query, limit=100)
    if not results:
        st.caption(f"「{query}」に一致するコメントなし")
        return
    st.markdown(f"**「{query}」** の検索結果: {len(results)}件")
    lines = []
    for comment, video_id, offset in results:
        mem = "🔴" if comment.is_member else "  "
        dt = comment.published_at.strftime("%Y-%m-%d %H:%M")
        link = yt_markdown(video_id, "▶", max(0, offset))
        text = comment.message_text[:100]
        sc = f" 💰{comment.super_chat_amount_text}" if comment.super_chat_amount_text else ""
        lines.append(f"`{mem}` {dt} {link}: {text}{sc}")
    st.markdown("\n".join(lines), unsafe_allow_html=True)


def show_dashboard():
    stats = _cached_stats()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("総視聴者数", stats.get("viewer_count", 0))
    col2.metric("メンバー数", stats.get("member_count", 0))
    col3.metric("記録配信数", stats.get("stream_count", 0))
    col4.metric("総コメント数", stats.get("comment_count", 0))
    col5.metric("スパチャ数", stats.get("superchat_count", 0))

    st.subheader("🏆 ランキングサマリー")
    rank_col1, rank_col2 = st.columns(2)
    with rank_col1:
        st.caption("古参 TOP5")
        oldest = _cached_rankings("oldest", 5)
        if oldest:
            df = pd.DataFrame(oldest)
            df["first_seen_at"] = pd.to_datetime(df["first_seen_at"]).dt.strftime("%Y-%m-%d")
            st.dataframe(df[["display_name", "first_seen_at", "comment_count"]].rename(
                columns={"display_name": "名前", "first_seen_at": "初コメント", "comment_count": "コメント数"}
            ), hide_index=True, use_container_width=True)
    with rank_col2:
        st.caption("スパチャ TOP5")
        sc = _cached_rankings("superchat", 5)
        if sc:
            df = pd.DataFrame(sc)
            st.dataframe(df[["display_name", "superchat_total", "comment_count"]].rename(
                columns={"display_name": "名前", "superchat_total": "総額(円)", "comment_count": "スパチャ数"}
            ), hide_index=True, use_container_width=True)


def show_viewers():
    st.subheader("👤 視聴者一覧")
    viewers = _cached_viewers()
    if not viewers:
        st.info("まだデータがありません。「配信一覧」からチャットを収集してください。")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        search = st.text_input("🔍 名前で検索", "")
    with col2:
        member_filter = st.selectbox("メンバー", ["すべて", "メンバーのみ"], index=0)
    with col3:
        sort_by = st.selectbox("並び替え", ["初コメントが古い順", "コメント数順", "名前順"], index=0)

    filtered = viewers
    if search:
        filtered = [v for v in filtered if search.lower() in v.display_name.lower()]
    if member_filter == "メンバーのみ":
        filtered = [v for v in filtered if v.is_member]

    if sort_by == "初コメントが古い順":
        filtered.sort(key=lambda v: v.first_seen_at or datetime.min)
    elif sort_by == "コメント数順":
        filtered.sort(key=lambda v: -v.comment_count)
    else:
        filtered.sort(key=lambda v: v.display_name)

    # Build DataFrame (B-2: st.dataframe instead of 6074 st.button() calls)
    df_data = []
    for v in filtered:
        df_data.append({
            "名前": v.display_name,
            "初コメント": v.first_seen_at.strftime("%Y-%m-%d") if v.first_seen_at else "?",
            "メンバー": "✅" if v.is_member else "",
            "コメント数": v.comment_count,
            "スパチャ額": f"¥{v.superchat_total:,}" if v.superchat_total > 0 else "",
        })
    df = pd.DataFrame(df_data)
    st.dataframe(df, hide_index=True, use_container_width=True)

    # Viewer detail: selectbox instead of 6000 buttons
    names = [v.display_name for v in filtered]
    if names:
        selected = st.selectbox("👤 詳細を見る視聴者を選択", [""] + names, key="viewer_selector")
        if selected:
            for v in filtered:
                if v.display_name == selected:
                    st.session_state["detail_channel_id"] = v.channel_id
                    break

    if "detail_channel_id" in st.session_state:
        show_viewer_detail(st.session_state["detail_channel_id"])


def show_viewer_detail(channel_id: str):
    v = get_viewer(channel_id)
    if not v:
        return

    with st.container(border=True):
        col1, col2 = st.columns([1, 4])
        with col1:
            if v.avatar_url:
                st.image(v.avatar_url, width=80)
        with col2:
            st.markdown(f"### {v.display_name}")
            cols = st.columns(4)
            cols[0].markdown(f"**初コメント**  {v.first_seen_at.strftime('%Y-%m-%d') if v.first_seen_at else '?'}")
            cols[1].markdown(f"**メンバー**  {'✅' if v.is_member else '❌'}")
            cols[2].markdown(f"**コメント数**  {v.comment_count}")
            if v.superchat_total > 0:
                cols[3].markdown(f"**スパチャ総額**  ¥{v.superchat_total:,}")

    events = get_membership_events_by_viewer(channel_id)
    if events:
        st.subheader("📅 メンバーシップ履歴")
        for ev in events:
            st.markdown(f"- {ev.occurred_at.strftime('%Y-%m-%d')}: **{ev.event_type}** (加入{ev.member_month}ヶ月)")

    st.subheader("💬 コメント履歴")
    result = get_comments_by_viewer(channel_id, limit=500)
    if result:
        lines = []
        for comment, video_id, offset in result[:200]:
            mem = "🔴" if comment.is_member else "  "
            dt = comment.published_at.strftime("%Y-%m-%d %H:%M")
            link = yt_markdown(video_id, "▶", max(0, offset))
            text = comment.message_text[:150]
            sc = f" 💰{comment.super_chat_amount_text}" if comment.super_chat_amount_text else ""
            lines.append(f"`{mem}` {dt} {link}: {text}{sc}")
        st.markdown("\n".join(lines), unsafe_allow_html=True)
    else:
        st.caption("コメント履歴なし")


def show_rankings():
    st.subheader("🏆 ランキング")

    rank_type = st.radio("ランキング種類", ["古参", "コメント数", "スパチャ"], horizontal=True)
    limit = st.slider("表示件数", 10, 100, 50)

    type_map = {"古参": "oldest", "コメント数": "comments", "スパチャ": "superchat"}
    rows = _cached_rankings(type_map[rank_type], limit)

    if not rows:
        st.info("データがまだありません。")
        return

    if rank_type == "古参":
        df = pd.DataFrame(rows)
        df["first_seen_at"] = pd.to_datetime(df["first_seen_at"]).dt.strftime("%Y-%m-%d")
        df = df.reset_index()
        df["index"] = df["index"] + 1
        st.dataframe(
            df[["index", "display_name", "first_seen_at", "comment_count"]].rename(
                columns={"index": "順位", "display_name": "名前", "first_seen_at": "初コメント", "comment_count": "コメント数"}
            ),
            hide_index=True, use_container_width=True,
        )
    elif rank_type == "コメント数":
        df = pd.DataFrame(rows)
        df = df.reset_index()
        df["index"] = df["index"] + 1
        st.dataframe(
            df[["index", "display_name", "comment_count", "first_seen_at"]].rename(
                columns={"index": "順位", "display_name": "名前", "comment_count": "コメント数", "first_seen_at": "初コメント"}
            ),
            hide_index=True, use_container_width=True,
        )
    elif rank_type == "スパチャ":
        df = pd.DataFrame(rows)
        df["superchat_total"] = df["superchat_total"].fillna(0).astype(int)
        df = df.reset_index()
        df["index"] = df["index"] + 1
        st.dataframe(
            df[["index", "display_name", "superchat_total", "comment_count"]].rename(
                columns={"index": "順位", "display_name": "名前", "superchat_total": "総額(円)", "comment_count": "スパチャ数"}
            ),
            hide_index=True, use_container_width=True,
        )


def show_streams():
    st.subheader("📹 配信一覧")

    streams = get_all_streams()
    if not streams:
        st.info("データベースに配信が登録されていません。")
        return

    for s in streams[:500]:
        link = yt_markdown(s.video_id, "▶")
        title = s.title[:80]
        date = s.published_at.strftime("%Y-%m-%d") if s.published_at else "?"
        dur = f"{s.duration_sec // 3600}h{(s.duration_sec % 3600) // 60:02d}m" if s.duration_sec else "?"
        mem = "🔒" if s.is_member_only else ""
        st.markdown(
            f"{link} `{date}` {dur} {mem} **{title}**  ({s.chat_count}コメ/{s.unique_viewers}人)",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        f"<div style='text-align: center; color: #888; font-size: 12px;'>"
        f"AyumiDB v{VERSION} | "
        f"<a href='{GITHUB_URL}' style='color: #4af;'>GitHub</a>"
        f"</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
