import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    get_stream_time_series, get_overall_time_series,
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

@st.cache_data(ttl=60)
def _cached_stream_time_series(stream_id: str, bucket_sec: int = 300):
    return get_stream_time_series(stream_id, bucket_sec)

@st.cache_data(ttl=60)
def _cached_overall_time_series():
    return get_overall_time_series()


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

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["ダッシュボード", "視聴者一覧", "ランキング", "配信一覧", "📈 全体推移"])

    with tab1:
        show_dashboard()
    with tab2:
        show_viewers()
    with tab3:
        show_rankings()
    with tab4:
        show_streams()
    with tab5:
        show_overall_trends()


def show_search_results(query: str):
    results = search_comments(query)
    if not results:
        st.caption(f"「{query}」に一致するコメントなし")
        return
    st.markdown(f"**「{query}」** の検索結果: {len(results)}件")
    rows = []
    for comment, video_id, offset, display_name in results:
        rows.append({
            "日時": comment.published_at.strftime("%Y-%m-%d %H:%M"),
            "名前": display_name,
            "コメント": comment.message_text[:120],
            "リンク": yt_link(video_id, max(0, offset)),
            "メンバー": "🔴" if comment.is_member else "",
            "スパチャ": comment.super_chat_amount_text or "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "リンク": st.column_config.LinkColumn("▶", display_text="▶", width="small"),
            "メンバー": st.column_config.Column(width="small"),
            "スパチャ": st.column_config.Column(width="small"),
        },
        hide_index=True,
        use_container_width=True,
    )


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
    result = get_comments_by_viewer(channel_id)
    if result:
        rows = []
        for comment, video_id, offset in result:
            rows.append({
                "日時": comment.published_at.strftime("%Y-%m-%d %H:%M"),
                "コメント": comment.message_text[:150],
                "リンク": yt_link(video_id, max(0, offset)),
                "メンバー": "🔴" if comment.is_member else "",
                "スパチャ": comment.super_chat_amount_text or "",
            })
        st.caption(f"全 {len(result)} 件")
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            column_config={
                "リンク": st.column_config.LinkColumn("▶", display_text="▶", width="small"),
                "メンバー": st.column_config.Column(width="small"),
                "スパチャ": st.column_config.Column(width="small"),
            },
            hide_index=True,
            use_container_width=True,
        )
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

    rows = []
    for s in streams:
        dur_min = (s.duration_sec // 60) if s.duration_sec else 0
        cph = round(s.chat_count / (s.duration_sec / 3600), 1) if s.duration_sec > 0 else 0
        vph = round(s.unique_viewers / (s.duration_sec / 3600), 1) if s.duration_sec > 0 else 0
        rows.append({
            "日時": s.published_at.strftime("%Y-%m-%d") if s.published_at else "?",
            "タイトル": s.title[:80],
            "時間(分)": dur_min,
            "コメント数": s.chat_count,
            "視聴者数": s.unique_viewers,
            "コメ/h": cph,
            "人/h": vph,
            "リンク": yt_link(s.video_id),
            "メン限": "🔒" if s.is_member_only else "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        column_config={
            "リンク": st.column_config.LinkColumn("▶", display_text="▶", width="small"),
            "メン限": st.column_config.Column(width="small"),
            "時間(分)": st.column_config.NumberColumn("時間(分)", help="分単位"),
        },
        hide_index=True,
        use_container_width=True,
    )

    # ----- Per-stream time-series charts -----
    st.markdown("---")
    st.subheader("📈 配信分析")
    options = [""] + [
        f"{s.published_at.strftime('%Y-%m-%d')} {s.title[:60]}"
        if s.published_at else s.title[:60]
        for s in streams
    ]
    selected_label = st.selectbox("分析する配信を選択", options, key="stream_analysis_selector")
    if selected_label:
        for s in streams:
            label = (
                f"{s.published_at.strftime('%Y-%m-%d')} {s.title[:60]}"
                if s.published_at else s.title[:60]
            )
            if label == selected_label:
                _show_stream_charts(s.video_id)
                break

    st.markdown("---")
    st.markdown(
        f"<div style='text-align: center; color: #888; font-size: 12px;'>"
        f"AyumiDB v{VERSION} | "
        f"<a href='{GITHUB_URL}' style='color: #4af;'>GitHub</a>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _show_stream_charts(video_id: str):
    data = _cached_stream_time_series(video_id, 300)
    if not data:
        st.caption("時系列データがありません")
        return
    df = pd.DataFrame(data)
    df["bucket_min"] = df["bucket_start"] / 60

    col1, col2 = st.columns(2)
    with col1:
        fig1 = px.bar(
            df, x="bucket_min", y="comment_count",
            labels={"bucket_min": "経過時間(分)", "comment_count": "コメント数"},
            title="コメント数推移（5分単位）",
        )
        fig1.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        fig2 = px.line(
            df, x="bucket_min", y="viewer_count",
            labels={"bucket_min": "経過時間(分)", "viewer_count": "発言人数"},
            title="発言人數推移（5分単位）",
            markers=True,
        )
        fig2.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig2, use_container_width=True)

    stream_info = get_stream(video_id)
    if stream_info:
        dur_str = (
            f"{stream_info.duration_sec // 3600}h{stream_info.duration_sec % 3600 // 60:02d}m"
            if stream_info.duration_sec else "?"
        )
        st.caption(
            f"配信時間: {dur_str} | "
            f"総コメント: {stream_info.chat_count} | "
            f"ユニーク視聴者: {stream_info.unique_viewers}"
        )


def show_overall_trends():
    st.subheader("📈 全体推移（月別）")
    data = _cached_overall_time_series()
    if not data.get("comments"):
        st.info("まだデータがありません。")
        return

    df_comments = pd.DataFrame(data["comments"])
    df_viewers = pd.DataFrame(data["viewers"])
    df_streams = pd.DataFrame(data["streams"])

    col1, col2 = st.columns(2)
    with col1:
        fig1 = px.bar(
            df_comments, x="month", y="cnt",
            labels={"month": "", "cnt": "コメント数"},
            title="月別コメント数",
        )
        fig1.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=40),
                          xaxis_tickangle=-45)
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        fig2 = px.line(
            df_viewers, x="month", y="cnt",
            labels={"month": "", "cnt": "視聴者数"},
            title="月別ユニーク視聴者数",
            markers=True,
        )
        fig2.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=40),
                          xaxis_tickangle=-45)
        st.plotly_chart(fig2, use_container_width=True)

    fig3 = px.bar(
        df_streams, x="month", y="cnt",
        labels={"month": "", "cnt": "配信数"},
        title="月別配信数",
    )
    fig3.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=40),
                      xaxis_tickangle=-45)
    st.plotly_chart(fig3, use_container_width=True)

    st.caption(
        f"期間: {df_comments['month'].iloc[0]} ～ {df_comments['month'].iloc[-1]} "
        f"（{len(df_comments)}ヶ月）"
    )


if __name__ == "__main__":
    main()
