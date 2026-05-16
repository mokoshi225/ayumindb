"""チャットJSONパーサー — 視聴者/コメント/メンバーシップイベントを抽出"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .models import Comment, MembershipEvent, Viewer

JST = timezone(timedelta(hours=9))


def parse_chat_file(filepath: Path) -> dict:
    """1配信分の.live_chat.jsonをパース

    Returns:
        dict with keys:
          - stream_id: str
          - viewers: dict[channel_id, Viewer]
          - comments: list[Comment]
          - membership_events: list[MembershipEvent]
          - superchat_count: int
    """
    stream_id = filepath.stem.replace(".live_chat", "")
    lines = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))

    viewers: dict[str, Viewer] = {}
    comments: list[Comment] = []
    membership_events: list[MembershipEvent] = []
    superchat_count = 0

    for msg in lines:
        actions = (
            msg.get("replayChatItemAction", {}).get("actions", [])
            if "replayChatItemAction" in msg
            else msg.get("actions", [])
        )
        for action in actions:
            item = _get_chat_item(action)
            if item is None:
                continue

            # --- 通常テキストメッセージ ---
            if "liveChatTextMessageRenderer" in item:
                r = item["liveChatTextMessageRenderer"]
                parsed = _parse_text_message(r, stream_id)
                if parsed:
                    comment, viewer = parsed
                    comments.append(comment)
                    _merge_viewer(viewers, viewer)

            # --- スーパーチャット ---
            if "liveChatPaidMessageRenderer" in item:
                r = item["liveChatPaidMessageRenderer"]
                parsed = _parse_superchat(r, stream_id)
                if parsed:
                    comment, viewer = parsed
                    comments.append(comment)
                    _merge_viewer(viewers, viewer)
                    superchat_count += 1

            # --- メンバーシップイベント ---
            if "liveChatMembershipItemRenderer" in item:
                r = item["liveChatMembershipItemRenderer"]
                parsed = _parse_membership_event(r, stream_id)
                if parsed:
                    event, viewer = parsed
                    membership_events.append(event)
                    _merge_viewer(viewers, viewer)

            # --- メンバーマイルストーン ---
            if "liveChatMemberMilestoneChatRenderer" in item:
                r = item["liveChatMemberMilestoneChatRenderer"]
                parsed = _parse_milestone_event(r, stream_id)
                if parsed:
                    event, viewer = parsed
                    membership_events.append(event)
                    _merge_viewer(viewers, viewer)

    return {
        "stream_id": stream_id,
        "viewers": viewers,
        "comments": comments,
        "membership_events": membership_events,
        "superchat_count": superchat_count,
    }


def _get_chat_item(action: dict) -> Optional[dict]:
    if "addChatItemAction" in action:
        return action["addChatItemAction"].get("item", {})
    if "addLiveChatTickerItemAction" in action:
        return action["addLiveChatTickerItemAction"].get("item", {})
    return None


def _parse_text_message(r: dict, stream_id: str) -> Optional[tuple[Comment, Viewer]]:
    channel_id = r.get("authorExternalChannelId", "")
    if not channel_id:
        return None

    name = r.get("authorName", {}).get("simpleText", "?")
    avatar = _get_avatar(r.get("authorPhoto", {}))
    ts_usec = int(r.get("timestampUsec", "0"))
    published_at = datetime.fromtimestamp(ts_usec / 1_000_000, tz=JST)
    msg_text = _extract_text(r.get("message", {}))

    badge_str = json.dumps(r.get("authorBadges", []))
    is_member = "sponsor" in badge_str.lower() or "member" in badge_str.lower()
    is_owner = "owner" in badge_str.lower()
    is_moderator = "moderator" in badge_str.lower()

    message_id = r.get("id", f"txt_{channel_id}_{ts_usec}")
    message_type = "textMessageEvent"
    superchat_amount = ""

    comment = Comment(
        message_id=message_id,
        viewer_id=channel_id,
        stream_id=stream_id,
        published_at=published_at,
        message_text=msg_text,
        message_type=message_type,
        is_member=is_member,
        super_chat_amount_text=superchat_amount,
    )

    viewer = Viewer(
        channel_id=channel_id,
        display_name=name,
        avatar_url=avatar,
        first_seen_at=published_at,
        is_member=is_member,
        is_owner=is_owner,
        is_moderator=is_moderator,
    )

    return comment, viewer


def _parse_superchat(r: dict, stream_id: str) -> Optional[tuple[Comment, Viewer]]:
    channel_id = r.get("authorExternalChannelId", "")
    if not channel_id:
        return None
    name = r.get("authorName", {}).get("simpleText", "?")
    avatar = _get_avatar(r.get("authorPhoto", {}))
    ts_usec = int(r.get("timestampUsec", "0"))
    published_at = datetime.fromtimestamp(ts_usec / 1_000_000, tz=JST)
    msg_text = _extract_text(r.get("message", {}))
    amount = r.get("purchaseAmountText", {}).get("simpleText", "")
    badge_str = json.dumps(r.get("authorBadges", []))
    is_member = "sponsor" in badge_str.lower()

    message_id = r.get("id", f"sc_{channel_id}_{ts_usec}")
    comment = Comment(
        message_id=message_id,
        viewer_id=channel_id,
        stream_id=stream_id,
        published_at=published_at,
        message_text=msg_text,
        message_type="superChatEvent",
        is_member=is_member,
        super_chat_amount_text=amount,
    )
    viewer = Viewer(
        channel_id=channel_id,
        display_name=name,
        avatar_url=avatar,
        first_seen_at=published_at,
        is_member=is_member,
    )
    return comment, viewer


def _parse_membership_event(r: dict, stream_id: str) -> Optional[tuple[MembershipEvent, Viewer]]:
    channel_id = r.get("authorExternalChannelId", "")
    if not channel_id:
        return None

    name = r.get("authorName", {}).get("simpleText", "?")
    avatar = _get_avatar(r.get("authorPhoto", {}))
    ts_usec = int(r.get("timestampUsec", "0"))
    published_at = datetime.fromtimestamp(ts_usec / 1_000_000, tz=JST)

    header_text = _extract_text(r.get("headerPrimaryText", {}))
    month_match = re.search(r"(\d+)\s*(month|ヶ月|months|month)", header_text, re.IGNORECASE)
    member_month = int(month_match.group(1)) if month_match else 0

    badge_str = json.dumps(r.get("authorBadges", []))
    is_member = True

    event = MembershipEvent(
        viewer_id=channel_id,
        stream_id=stream_id,
        event_type="milestone" if member_month > 1 else "join",
        member_level="",
        member_month=member_month,
        occurred_at=published_at,
    )

    # 加入月を逆算: 配信日 - member_month
    if member_month > 0:
        estimated_join = published_at - timedelta(days=30 * (member_month - 0.5))
        viewer = Viewer(
            channel_id=channel_id,
            display_name=name,
            avatar_url=avatar,
            first_seen_at=estimated_join,
            is_member=True,
            first_member_at=estimated_join,
        )
    else:
        viewer = Viewer(
            channel_id=channel_id,
            display_name=name,
            avatar_url=avatar,
            first_seen_at=published_at,
            is_member=True,
            first_member_at=published_at,
        )

    return event, viewer


def _parse_milestone_event(r: dict, stream_id: str) -> Optional[tuple[MembershipEvent, Viewer]]:
    """memberMilestoneChatRenderer のパース（チャット内のメンバーマイルストーン通知）"""
    channel_id = r.get("authorExternalChannelId", "")
    if not channel_id:
        return None

    name = r.get("authorName", {}).get("simpleText", "?")
    avatar = _get_avatar(r.get("authorPhoto", {}))
    ts_usec = int(r.get("timestampUsec", "0"))
    published_at = datetime.fromtimestamp(ts_usec / 1_000_000, tz=JST)

    member_month = r.get("memberMilestoneChatDetails", {}).get("memberMonth", 0)
    level = r.get("memberMilestoneChatDetails", {}).get("memberLevelName", "")

    event = MembershipEvent(
        viewer_id=channel_id,
        stream_id=stream_id,
        event_type="milestone",
        member_level=level,
        member_month=member_month,
        occurred_at=published_at,
    )

    estimated_join = published_at - timedelta(days=30 * (member_month - 0.5)) if member_month > 0 else published_at
    viewer = Viewer(
        channel_id=channel_id,
        display_name=name,
        avatar_url=avatar,
        first_seen_at=estimated_join,
        is_member=True,
        first_member_at=estimated_join,
    )

    return event, viewer


def _extract_text(obj: dict) -> str:
    runs = obj.get("runs", [])
    return "".join(part.get("text", "") for part in runs)


def _get_avatar(photo_obj: dict) -> str:
    thumbs = photo_obj.get("thumbnails", [])
    return thumbs[-1]["url"] if thumbs else ""


def _merge_viewer(viewers: dict[str, Viewer], new: Viewer):
    if new.channel_id in viewers:
        existing = viewers[new.channel_id]
        if new.first_seen_at and existing.first_seen_at:
            existing.first_seen_at = min(existing.first_seen_at, new.first_seen_at)
        existing.is_member = existing.is_member or new.is_member
        if new.first_member_at:
            if existing.first_member_at is None or new.first_member_at < existing.first_member_at:
                existing.first_member_at = new.first_member_at
        existing.is_owner = existing.is_owner or new.is_owner
        existing.is_moderator = existing.is_moderator or new.is_moderator
        if new.display_name and new.display_name != "?":
            existing.display_name = new.display_name
        if new.avatar_url:
            existing.avatar_url = new.avatar_url
    else:
        viewers[new.channel_id] = new
