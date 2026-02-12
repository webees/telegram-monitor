"""
数据模型
所有数据结构定义
"""

# ── models/config.py ──
"""
监控配置相关数据模型
"""

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from enum import Enum


class MatchType(Enum):
    EXACT = "exact"
    PARTIAL = "partial" 
    REGEX = "regex"


class MonitorMode(Enum):
    MANUAL = "manual"
    AI = "ai"


class ReplyMode(Enum):
    REPLY = "reply"
    SEND = "send"


class ReplyContentType(Enum):
    CUSTOM = "custom"
    AI = "ai"


class ExecutionMode(Enum):
    MERGE = "merge"
    FIRST_MATCH = "first_match"
    ALL = "all"


@dataclass
class BaseMonitorConfig:
    chats: List[int] = field(default_factory=list)
    users: List[Union[int, str]] = field(default_factory=list)
    user_option: Optional[str] = None
    blocked_users: List[str] = field(default_factory=list)
    blocked_channels: List[int] = field(default_factory=list)
    blocked_bots: List[int] = field(default_factory=list)
    match_bots: List[int] = field(default_factory=list)
    match_channels: List[int] = field(default_factory=list)
    bot_ids: List[int] = field(default_factory=list)
    channel_ids: List[int] = field(default_factory=list)
    group_ids: List[int] = field(default_factory=list)
    email_notify: bool = False
    auto_forward: bool = False
    forward_targets: List[int] = field(default_factory=list)
    log_file: Optional[str] = None
    max_executions: Optional[int] = None
    execution_count: int = 0
    enhanced_forward: bool = False
    max_download_size_mb: Optional[float] = None
    download_folder: str = "data/dl"
    priority: int = 50
    active: bool = True
    execution_mode: str = "merge"
    
    def is_execution_limit_reached(self) -> bool:
        if self.max_executions is None:
            return False
        return self.execution_count >= self.max_executions
    
    def increment_execution(self):
        self.execution_count += 1
    
    def reset_execution_count(self):
        self.execution_count = 0
    
    def pause_and_reset(self):
        self.active = False
        self.execution_count = 0


@dataclass
class KeywordConfig(BaseMonitorConfig):
    keyword: str = ""
    match_type: MatchType = MatchType.PARTIAL
    reply_enabled: bool = False
    reply_texts: List[str] = field(default_factory=list)
    reply_delay_min: float = 0
    reply_delay_max: float = 0
    reply_mode: ReplyMode = ReplyMode.REPLY
    reply_content_type: ReplyContentType = ReplyContentType.CUSTOM
    ai_reply_prompt: str = ""
    regex_send_target_id: Optional[int] = None
    regex_send_random_offset: int = 0
    regex_send_delete: bool = False
    matched_keyword: Optional[str] = None
    
    def __post_init__(self):
        if isinstance(self.match_type, str):
            self.match_type = MatchType(self.match_type)
        if isinstance(self.reply_mode, str):
            self.reply_mode = ReplyMode(self.reply_mode)
        if isinstance(self.reply_content_type, str):
            self.reply_content_type = ReplyContentType(self.reply_content_type)


@dataclass
class FileConfig(BaseMonitorConfig):
    file_extension: str = ""
    save_folder: Optional[str] = None
    min_size: Optional[float] = None
    max_size: Optional[float] = None
    
    def is_size_valid(self, file_size_mb: float) -> bool:
        if self.min_size is not None and file_size_mb < self.min_size:
            return False
        if self.max_size is not None and file_size_mb > self.max_size:
            return False
        return True


@dataclass
class ButtonConfig(BaseMonitorConfig):
    button_keyword: str = ""
    mode: MonitorMode = MonitorMode.MANUAL
    ai_prompt: str = ""
    
    def __post_init__(self):
        if isinstance(self.mode, str):
            self.mode = MonitorMode(self.mode)


@dataclass
class AllMessagesConfig(BaseMonitorConfig):
    chat_id: int = 0
    reply_enabled: bool = False
    reply_texts: List[str] = field(default_factory=list)
    reply_delay_min: float = 0
    reply_delay_max: float = 0
    reply_mode: ReplyMode = ReplyMode.REPLY
    reply_content_type: ReplyContentType = ReplyContentType.CUSTOM
    ai_reply_prompt: str = ""
    
    def __post_init__(self):
        if isinstance(self.reply_mode, str):
            self.reply_mode = ReplyMode(self.reply_mode)
        if isinstance(self.reply_content_type, str):
            self.reply_content_type = ReplyContentType(self.reply_content_type)


@dataclass
class ImageButtonConfig(BaseMonitorConfig):
    ai_prompt: str = "分析图片和按钮内容，判断是否需要点击某个按钮"
    button_keywords: List[str] = None
    download_images: bool = True
    auto_reply: bool = False
    confidence_threshold: float = 0.7
    
    def __post_init__(self):
        if self.button_keywords is None:
            self.button_keywords = []


@dataclass
class ScheduledMessageConfig:
    job_id: str
    target_id: int
    message: str
    cron: str
    random_offset: int = 0
    delete_after_sending: bool = False
    account_id: Optional[str] = None
    max_executions: Optional[int] = None
    execution_count: int = 0
    use_ai: bool = False
    ai_prompt: Optional[str] = None
    schedule_mode: str = "cron"
    
    def is_execution_limit_reached(self) -> bool:
        if self.max_executions is None:
            return False
        return self.execution_count >= self.max_executions
    
    def increment_execution(self):
        self.execution_count += 1


@dataclass 
class AIMonitorConfig(BaseMonitorConfig):
    ai_prompt: str = ""
    confidence_threshold: float = 0.7
    ai_model: str = "gpt-4o"
    reply_enabled: bool = False
    reply_texts: List[str] = field(default_factory=list)
    reply_delay_min: float = 0
    reply_delay_max: float = 0
    reply_mode: ReplyMode = ReplyMode.REPLY
    ai_reply_prompt: str = ""
    ai_response_content: Optional[str] = None
    
    def __post_init__(self):
        if not self.ai_prompt:
            self.ai_prompt = "请判断以下消息是否符合监控条件，回答 yes 或 no"
        if isinstance(self.reply_mode, str):
            self.reply_mode = ReplyMode(self.reply_mode)


@dataclass
class MonitorConfig:
    keyword_configs: Dict[str, KeywordConfig] = field(default_factory=dict)
    file_configs: Dict[str, FileConfig] = field(default_factory=dict)
    button_configs: Dict[str, ButtonConfig] = field(default_factory=dict)
    all_message_configs: Dict[int, AllMessagesConfig] = field(default_factory=dict)
    ai_monitor_configs: Dict[str, AIMonitorConfig] = field(default_factory=dict)
    image_button_configs: List[ImageButtonConfig] = field(default_factory=list)
    scheduled_message_configs: List[ScheduledMessageConfig] = field(default_factory=list)
    channel_in_group_configs: List[int] = field(default_factory=list)
    
    def add_keyword_config(self, keyword: str, config: KeywordConfig):
        self.keyword_configs[keyword] = config
    
    def remove_keyword_config(self, keyword: str) -> bool:
        if keyword in self.keyword_configs:
            del self.keyword_configs[keyword]
            return True
        return False
    
    def get_keyword_config(self, keyword: str) -> Optional[KeywordConfig]:
        return self.keyword_configs.get(keyword)
    
    def add_file_config(self, extension: str, config: FileConfig):
        self.file_configs[extension] = config
    
    def remove_file_config(self, extension: str) -> bool:
        if extension in self.file_configs:
            del self.file_configs[extension]
            return True
        return False
    
    def get_file_config(self, extension: str) -> Optional[FileConfig]:
        return self.file_configs.get(extension)
    
    def to_dict(self) -> Dict[str, Any]:
        pass
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MonitorConfig':
        pass 

# ── models/account.py ──
"""
账号相关数据模型
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from telethon import TelegramClient
import json


@dataclass
class AccountConfig:
    phone: str
    api_id: int
    api_hash: str
    proxy: Optional[tuple] = None
    session_name: str = ""
    
    def __post_init__(self):
        if not self.session_name:
            self.session_name = f"session_{self.phone.replace('+', '')}"


@dataclass
class Account:
    account_id: str
    config: AccountConfig
    client: Optional[TelegramClient] = None
    own_user_id: Optional[int] = None
    monitor_active: bool = False
    monitor_configs: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.monitor_configs:
            self.monitor_configs = {
                "keyword_config": {},
                "file_extension_config": {},
                "all_messages_config": {},
                "button_keyword_config": {},
                "image_button_monitor": [],
                "scheduled_messages": [],
                "channel_in_group_config": []
            }
    
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()
    
    def is_authorized(self) -> bool:
        return self.own_user_id is not None
    
    async def check_validity(self) -> tuple[bool, str]:
        if not self.client:
            return False, "disconnected"
        
        try:
            if not self.client.is_connected():
                return False, "disconnected"
            
            if not await self.client.is_user_authorized():
                return False, "unauthorized"
            
            try:
                me = await self.client.get_me()
                if me and me.id:
                    return True, "active"
                else:
                    return False, "invalid"
            except Exception as e:
                error_str = str(e).lower()
                if "user deactivated" in error_str or "banned" in error_str:
                    return False, "banned"
                elif "auth key unregistered" in error_str:
                    return False, "unauthorized"
                elif "session revoked" in error_str:
                    return False, "session_revoked"
                else:
                    return False, "error"
                    
        except Exception as e:
            return False, "error"
    
    def get_status_display(self, status: str) -> str:
        status_map = {
            "active": "在线",
            "disconnected": "离线", 
            "unauthorized": "未授权",
            "banned": "已封禁",
            "session_revoked": "会话失效",
            "invalid": "账号无效",
            "error": "连接错误",
            "connecting": "连接中"
        }
        return status_map.get(status, "未知")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "phone": self.config.phone,
            "api_id": self.config.api_id,
            "api_hash": self.config.api_hash,
            "proxy": self.config.proxy,
            "session_name": self.config.session_name,
            "own_user_id": self.own_user_id,
            "monitor_active": self.monitor_active,
            "monitor_configs": self.monitor_configs
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Account':
        config = AccountConfig(
            phone=data["phone"],
            api_id=data["api_id"],
            api_hash=data["api_hash"],
            proxy=data.get("proxy"),
            session_name=data.get("session_name", "")
        )
        
        account = cls(
            account_id=data["account_id"],
            config=config,
            own_user_id=data.get("own_user_id"),
            monitor_active=data.get("monitor_active", False),
            monitor_configs=data.get("monitor_configs", {})
        )
        
        return account
    
    def get_monitor_config(self, config_type: str) -> Dict[str, Any]:
        return self.monitor_configs.get(config_type, {})
    
    def update_monitor_config(self, config_type: str, config_data: Dict[str, Any]):
        self.monitor_configs[config_type] = config_data
    
    def add_monitor_config(self, config_type: str, key: str, config: Dict[str, Any]):
        if config_type not in self.monitor_configs:
            self.monitor_configs[config_type] = {}
        self.monitor_configs[config_type][key] = config
    
    def remove_monitor_config(self, config_type: str, key: str) -> bool:
        if config_type in self.monitor_configs and key in self.monitor_configs[config_type]:
            del self.monitor_configs[config_type][key]
            return True
        return False 

# ── models/message.py ──
"""
消息相关数据模型
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from telethon.tl.types import User, Channel, Chat
from telethon import events


@dataclass
class MessageSender:
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_bot: bool = False
    is_channel: bool = False
    title: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        if self.title:
            return self.title
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) if parts else "未知用户"
    
    @classmethod
    def from_telethon_entity(cls, entity) -> 'MessageSender':
        if isinstance(entity, User):
            return cls(
                id=entity.id,
                username=entity.username,
                first_name=entity.first_name,
                last_name=entity.last_name,
                is_bot=entity.bot or False,
                is_channel=False
            )
        elif isinstance(entity, (Channel, Chat)):
            return cls(
                id=entity.id,
                username=getattr(entity, 'username', None),
                title=entity.title,
                is_bot=False,
                is_channel=isinstance(entity, Channel)
            )
        else:
            return cls(
                id=getattr(entity, 'id', 0),
                username=getattr(entity, 'username', None),
                first_name="未知",
                is_bot=False,
                is_channel=False
            )


@dataclass
class MessageMedia:
    has_media: bool = False
    media_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_extension: Optional[str] = None
    mime_type: Optional[str] = None
    
    @property
    def file_size_mb(self) -> Optional[float]:
        if self.file_size:
            return self.file_size / (1024 * 1024)
        return None


@dataclass
class MessageButton:
    text: str
    row: int
    col: int
    data: Optional[str] = None


@dataclass
class TelegramMessage:
    message_id: int
    chat_id: int
    sender: MessageSender
    text: str
    timestamp: datetime
    media: Optional[MessageMedia] = None
    buttons: List[List[MessageButton]] = field(default_factory=list)
    is_forwarded: bool = False
    forward_from_channel_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    
    @property
    def text_lower(self) -> str:
        return self.text.lower().strip()
    
    @property
    def has_buttons(self) -> bool:
        return len(self.buttons) > 0
    
    @property
    def button_texts(self) -> List[str]:
        texts = []
        for row in self.buttons:
            for button in row:
                texts.append(button.text.strip())
        return texts
    
    def get_button_by_text(self, text: str, exact_match: bool = False) -> Optional[MessageButton]:
        search_text = text.lower()
        for row in self.buttons:
            for button in row:
                button_text = button.text.lower()
                if exact_match:
                    if button_text == search_text:
                        return button
                else:
                    if search_text in button_text:
                        return button
        return None
    
    @classmethod
    def from_telethon_event(cls, event: events.NewMessage, sender: MessageSender) -> 'TelegramMessage':
        message = event.message
        
        media = None
        if message.media:
            media = MessageMedia(has_media=True)
            if hasattr(message.media, 'document'):
                doc = message.media.document
                media.file_size = doc.size
                media.mime_type = doc.mime_type
                
                for attr in doc.attributes:
                    if hasattr(attr, 'file_name'):
                        media.file_name = attr.file_name
                        if '.' in attr.file_name:
                            media.file_extension = '.' + attr.file_name.split('.')[-1].lower()
                        break
                
                if media.mime_type:
                    if media.mime_type.startswith('image/'):
                        media.media_type = 'image'
                    elif media.mime_type.startswith('video/'):
                        media.media_type = 'video'
                    elif media.mime_type.startswith('audio/'):
                        media.media_type = 'audio'
                    else:
                        media.media_type = 'document'
            elif hasattr(message.media, 'photo'):
                media.media_type = 'photo'
        
        buttons = []
        if message.buttons:
            for row_idx, row in enumerate(message.buttons):
                button_row = []
                for col_idx, button in enumerate(row):
                    msg_button = MessageButton(
                        text=button.text,
                        row=row_idx,
                        col=col_idx,
                        data=getattr(button, 'data', None)
                    )
                    button_row.append(msg_button)
                buttons.append(button_row)
        
        is_forwarded = message.fwd_from is not None
        forward_from_channel_id = None
        if is_forwarded and message.fwd_from:
            if hasattr(message.fwd_from, 'from_chat') and message.fwd_from.from_chat:
                forward_from_channel_id = message.fwd_from.from_chat.id
            elif hasattr(message.fwd_from, 'from_id') and message.fwd_from.from_id:
                forward_from_channel_id = getattr(message.fwd_from.from_id, 'channel_id', None)
        
        return cls(
            message_id=message.id,
            chat_id=event.chat_id,
            sender=sender,
            text=message.text or '',
            timestamp=message.date,
            media=media,
            buttons=buttons,
            is_forwarded=is_forwarded,
            forward_from_channel_id=forward_from_channel_id,
            reply_to_message_id=message.reply_to_msg_id
        )


@dataclass
class MessageEvent:
    account_id: str
    message: TelegramMessage
    event_type: str = "new_message"
    processed: bool = False
    
    @property
    def unique_id(self) -> str:
        return f"{self.account_id}_{self.message.chat_id}_{self.message.message_id}" 