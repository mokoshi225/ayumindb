import streamlit as st
import pandas as pd
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ayumindb import VERSION, GITHUB_URL
from ayumindb.db import (
    init_db, get_all_viewers, get_viewer, get_all_streams, get_stream,
    get_comments_by_viewer, get_comments_by_stream, get_membership_events_by_viewer,
    get_stats, get_rankings,
)

st.set_page_config(page_title="AyumiDB", layout="wide", page_icon="📊")


def main():
    init_db()
    st.title("📊 あゆみんch 視聴者データベース")

    tab1, tab2, tab3, tab4 = st.tabs(["ダッシュボード", "視聴者一覧", "ランキング", "配信一覧"])

    with tab1:
        show_dashboard()
    with tab2:
        show_viewers()
    with tab3:
        show_rankings()
    with tab4:
        show_streams()


def show_dashboard():
    stats = get_stats()
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
        oldest = get_rankings("oldest", 5)
        if oldest:
            df = pd.DataFrame(oldest)
            df["first_seen_at"] = pd.to_datetime(df["first_seen_at"]).dt.strftime("%Y-%m-%d")
            st.dataframe(df[["display_name", "first_seen_at", "comment_count"]].rename(
                columns={"display_name": "名前", "first_seen_at": "初コメント", "comment_count": "コメント数"}
            ), hide_index=True, use_container_width=True)
    with rank_col2:
        st.caption("スパチャ TOP5")
        sc = get_rankings("superchat", 5)
        if sc:
            df = pd.DataFrame(sc)
            st.dataframe(df[["display_name", "superchat_total", "comment_count"]].rename(
                columns={"display_name": "名前", "superchat_total": "総額(円)", "comment_count": "スパチャ数"}
            ), hide_index=True, use_container_width=True)


def show_viewers():
    st.subheader("👤 視聴者一覧")

    viewers = get_all_viewers()
    if not viewers:
        st.info("まだデータがありません。「配信一覧」からチャットを収集してください。")
        return

    df = pd.DataFrame([{
        "channel_id": v.channel_id,
        "名前": v.display_name,
        "初コメント": v.first_seen_at.strftime("%Y-%m-%d") if v.first_seen_at else "?",
        "メンバー": "✅" if v.is_member else "",
        "コメント数": v.comment_count,
        "スパチャ額": f"¥{v.superchat_total:,}" if v.superchat_total > 0 else "",
    } for v in viewers])

    col1, col2, col3 = st.columns(3)
    with col1:
        search = st.text_input("🔍 名前で検索", "")
    with col2:
        member_filter = st.selectbox("メンバー", ["すべて", "メンバーのみ"], index=0)
    with col3:
        sort_by = st.selectbox("並び替え", ["初コメントが古い順", "コメント数順", "名前順"], index=0)

    if search:
        df = df[df["名前"].str.contains(search, case=False, na=False)]
    if member_filter == "メンバーのみ":
        df = df[df["メンバー"] == "✅"]

    sort_map = {
        "初コメントが古い順": ("初コメント", True),
        "コメント数順": ("コメント数", False),
        "名前順": ("名前", True),
    }
    sort_col, sort_asc = sort_map[sort_by]
    df = df.sort_values(sort_col, ascending=sort_asc)

    st.dataframe(df, hide_index=True, use_container_width=True)

    st.subheader("👤 視聴者詳細")
    selected_name = st.selectbox(
        "視聴者を選択", [v.display_name for v in viewers],
        index=None, placeholder="選択してください..."
    )
    if selected_name:
        matched = [v for v in viewers if v.display_name == selected_name]
        if matched:
            show_viewer_detail(matched[0].channel_id)


def show_viewer_detail(channel_id: str):
    v = get_viewer(channel_id)
    if not v:
        return

    col1, col2 = st.columns([1, 3])
    with col1:
        if v.avatar_url:
            st.image(v.avatar_url, width=80)
    with col2:
        st.markdown(f"### {v.display_name}")
        st.markdown(f"**初コメント:** {v.first_seen_at.strftime('%Y-%m-%d %H:%M') if v.first_seen_at else '?'}")
        st.markdown(f"**メンバー:** {'✅ 加入中' if v.is_member else '❌'}")
        if v.first_member_at:
            st.markdown(f"**メンバー加入（推定）:** {v.first_member_at.strftime('%Y-%m-%d')}")
        st.markdown(f"**総コメント数:** {v.comment_count}")
        if v.superchat_total > 0:
            st.markdown(f"**スパチャ総額:** ¥{v.superchat_total:,}")

    events = get_membership_events_by_viewer(channel_id)
    if events:
        st.subheader("📅 メンバーシップ履歴")
        for ev in events:
            st.markdown(f"- {ev.occurred_at.strftime('%Y-%m-%d')}: **{ev.event_type}** (加入{ev.member_month}ヶ月)")

    st.subheader("💬 コメント履歴")
    comments = get_comments_by_viewer(channel_id, limit=200)
    if comments:
        for c in comments[:50]:
            emoji = "🔴" if c.is_member else ""
            st.markdown(f"> {emoji} **{c.published_at.strftime('%Y-%m-%d %H:%M')}**")
            st.markdown(f"> {c.message_text[:200]}")
            if c.super_chat_amount_text:
                st.markdown(f"> 💰 {c.super_chat_amount_text}")
            st.divider()
    else:
        st.caption("コメント履歴なし")


def show_rankings():
    st.subheader("🏆 ランキング")

    rank_type = st.radio("ランキング種類", ["古参", "コメント数", "スパチャ"], horizontal=True)
    limit = st.slider("表示件数", 10, 100, 50)

    type_map = {"古参": "oldest", "コメント数": "comments", "スパチャ": "superchat"}
    rows = get_rankings(type_map[rank_type], limit)

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

    df = pd.DataFrame([{
        "video_id": s.video_id,
        "title": s.title[:60],
        "日時": s.published_at.strftime("%Y-%m-%d") if s.published_at else "?",
        "時間": f"{s.duration_sec // 3600}h{(s.duration_sec % 3600) // 60:02d}m" if s.duration_sec else "?",
        "コメント数": s.chat_count,
        "視聴者数": s.unique_viewers,
        "メン限": "🔒" if s.is_member_only else "",
    } for s in streams])

    st.dataframe(df, hide_index=True, use_container_width=True)


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
