"""データクラス定義"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Viewer:
    channel_id: str
    display_name: str = ""
    avatar_url: str = ""
    first_seen_at: Optional[datetime] = None
    is_member: bool = False
    first_member_at: Optional[datetime] = None
    is_owner: bool = False
    is_moderator: bool = False
    comment_count: int = 0
    superchat_total: int = 0  # 円（概算）


@dataclass
class Stream:
    video_id: str
    title: str = ""
    published_at: Optional[datetime] = None
    live_chat_id: str = ""
    duration_sec: int = 0
    chat_count: int = 0
    unique_viewers: int = 0
    is_member_only: bool = False
    collection_status: str = "pending"


@dataclass
class Comment:
    message_id: str
    viewer_id: str
    stream_id: str
    published_at: datetime
    message_text: str = ""
    message_type: str = "textMessageEvent"  # textMessageEvent, superChatEvent, memberMilestoneChatEvent, etc.
    is_member: bool = False
    super_chat_amount_text: str = ""


@dataclass
class MembershipEvent:
    viewer_id: str
    stream_id: str
    event_type: str  # join, milestone, gift_received
    member_level: str = ""
    member_month: int = 0  # 加入からの月数
    occurred_at: datetime = field(default_factory=datetime.now)
