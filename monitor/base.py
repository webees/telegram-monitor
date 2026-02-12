"""
基础监控器 - 应用策略模式和模板方法模式
定义监控器的基本接口和通用逻辑
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum

from core.model import TelegramMessage, MessageEvent, Account
from core.model import BaseMonitorConfig
from core.log import get_logger


class MonitorResult(Enum):
    NO_MATCH = "no_match"
    MATCHED = "matched"
    BLOCKED = "blocked"
    LIMIT_REACHED = "limit_reached"
    ERROR = "error"


@dataclass
class MonitorAction:
    result: MonitorResult
    actions_taken: List[str]
    message: str = ""
    error: Optional[Exception] = None


class BaseMonitor(ABC):
    
    def __init__(self, config: BaseMonitorConfig):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
    
    async def process_message(self, message_event: MessageEvent, account: Account) -> MonitorAction:
        try:
            if hasattr(self.config, 'active') and self.config.active is False:
                self.logger.debug(f"监控器已暂停，跳过处理")
                return MonitorAction(
                    result=MonitorResult.NO_MATCH,
                    actions_taken=[],
                    message="监控器已暂停"
                )
            
            if not self._check(message_event, account):
                return MonitorAction(
                    result=MonitorResult.NO_MATCH,
                    actions_taken=[],
                    message="消息不符合处理条件"
                )
            
            if self._is_blocked(message_event):
                return MonitorAction(
                    result=MonitorResult.BLOCKED,
                    actions_taken=[],
                    message="消息被屏蔽规则拦截"
                )
            
            if self.config.is_execution_limit_reached():
                return MonitorAction(
                    result=MonitorResult.LIMIT_REACHED,
                    actions_taken=[],
                    message="已达到最大执行次数"
                )
            
            if not await self._match(message_event, account):
                return MonitorAction(
                    result=MonitorResult.NO_MATCH,
                    actions_taken=[],
                    message="消息不匹配监控条件"
                )
            
            
            actions_taken = await self._execute_actions(message_event, account)
            
            await self._log_trigger(message_event, account)
            
            if actions_taken:
                self._log_result(message_event, account, actions_taken)
            
            return MonitorAction(
                result=MonitorResult.MATCHED,
                actions_taken=actions_taken,
                message="消息匹配并执行了相关动作"
            )
            
        except Exception as e:
            self.logger.error(f"处理消息时出错: {e}")
            return MonitorAction(
                result=MonitorResult.ERROR,
                actions_taken=[],
                message=f"处理消息时出错: {str(e)}",
                error=e
            )
    
    def _check(self, message_event: MessageEvent, account: Account) -> bool:
        message = message_event.message
        
        if message.sender.id == account.own_user_id:
            return False
        
        if self.config.chats and message.chat_id not in self.config.chats:
            self.logger.debug(f"消息来源聊天 {message.chat_id} 不在监控列表 {self.config.chats} 中")
            return False
            
        self.logger.debug(f"✅ 消息来源聊天 {message.chat_id} 在监控列表中")
        
        if not self._match_user(message.sender):
            return False

        if not self._match_chat(message_event):
            self.logger.debug(f"消息因聊天来源过滤失败，聊天ID: {message.chat_id}")
            return False

        self.logger.debug(f"消息通过所有过滤条件，聊天ID: {message.chat_id}, 发送者: {message.sender.id if message.sender else 'None'}")
        return True
    
    def _match_user(self, sender) -> bool:
        if self.config.users:
            user_option = self.config.user_option
            
            if user_option == '1':
                sender_id = sender.id
                sender_id_str = str(sender_id)
                if sender_id_str.startswith("-100"):
                    short_id = sender_id_str[4:]
                else:
                    short_id = sender_id_str
                
                user_set_str = {str(x) for x in self.config.users}
                if not (sender_id_str in user_set_str or short_id in user_set_str):
                    return False
                    
            elif user_option == '2':
                sender_username = getattr(sender, 'username', '').lower()
                if sender_username not in {str(u).lower() for u in self.config.users}:
                    return False
                    
            elif user_option == '3':
                if hasattr(sender, 'first_name'):
                    sender_full = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
                else:
                    sender_full = getattr(sender, 'title', '').strip()
                if sender_full not in {str(u) for u in self.config.users}:
                    return False
        
        return True
        
    def _match_chat(self, message_event: MessageEvent) -> bool:
        message = message_event.message
        chat_id = message.chat_id
        sender = message.sender
        
        if self.logger.isEnabledFor(logging.DEBUG):
            sender_info = f"发送者ID: {sender.id if sender else 'None'}, Bot: {getattr(sender, 'bot', False) if sender else False}"
            self.logger.debug(f"[过滤检查] 聊天ID: {chat_id}, {sender_info}")
        
        has_specific_ids = bool(self.config.bot_ids or self.config.channel_ids or self.config.group_ids)
        
        if has_specific_ids:
            self.logger.info(f"🔍 [精确ID过滤] 配置 - Bot: {self.config.bot_ids}, 频道: {self.config.channel_ids}, 群组: {self.config.group_ids}")
            
            sender_id = sender.id if sender else 0
            sender_is_bot = getattr(sender, 'bot', False) if sender else False
            
            self.logger.info(f"🔍 [ID匹配检查] 聊天ID: {chat_id}, 发送者ID: {sender_id}, 是Bot: {sender_is_bot}")
            
            id_matched = False
            
            if self.config.bot_ids and sender_is_bot:
                if sender_id in self.config.bot_ids:
                    id_matched = True
                    self.logger.debug(f"✅ 消息匹配Bot ID过滤: {sender_id}")
            
            if self.config.channel_ids:
                for config_id in self.config.channel_ids:
                    self.logger.debug(f"🔍 检查配置ID {config_id} 与发送者ID {sender_id}")
                    
                    if chat_id == config_id:
                        id_matched = True
                        self.logger.debug(f"✅ 聊天ID直接匹配配置ID: {chat_id}")
                        break
                    
                    if config_id < 0 and str(config_id).startswith("-100"):
                        channel_sender_id = abs(config_id) - 1000000000000
                        if sender_id == channel_sender_id:
                            id_matched = True
                            self.logger.debug(f"✅ 发送者ID匹配频道ID: {sender_id} (频道: {config_id})")
                            break
                    
                    full_channel_id = -1000000000000 - abs(sender_id)
                    if config_id == full_channel_id:
                        id_matched = True
                        self.logger.debug(f"✅ 发送者ID通过格式转换匹配频道ID: {sender_id} -> {full_channel_id}")
                        break
                

            
            if hasattr(self.config, 'group_ids') and self.config.group_ids:
                for group_id in self.config.group_ids:
                    if sender_id == group_id or chat_id == group_id:
                        id_matched = True
                        self.logger.debug(f"✅ 匹配群组ID过滤（兼容模式）: {group_id}")
                        break
            
            if not id_matched:
                self.logger.info(f"❌ [精确ID过滤] 发送者 {sender_id} 不匹配配置的任何ID，消息被拦截")
                self.logger.info(f"💡 配置的ID列表 - Bot: {self.config.bot_ids}, 频道: {self.config.channel_ids}, 群组: {self.config.group_ids}")
                return False
            else:
                self.logger.info(f"✅ [精确ID过滤] 发送者 {sender_id} 匹配成功")
        else:
            self.logger.debug(f"[无精确ID配置] 允许所有聊天来源")
        
        return True
    
    def _is_blocked(self, message_event: MessageEvent) -> bool:
        message = message_event.message
        sender = message.sender
        chat_id = message.chat_id
        
        if sender and str(sender.id) in self.config.blocked_users:
            self.logger.debug(f"消息被用户黑名单拦截: {sender.id}")
            return True
        
        if sender and getattr(sender, 'is_bot', False) and sender.id in self.config.blocked_bots:
            self.logger.debug(f"消息被Bot黑名单拦截: {sender.id}")
            return True
        
        if chat_id in self.config.blocked_channels:
            self.logger.debug(f"消息被频道/群组黑名单拦截: {chat_id}")
            return True
        
        if message.forward_from_channel_id and message.forward_from_channel_id in self.config.blocked_channels:
            self.logger.debug(f"消息被转发来源黑名单拦截: {message.forward_from_channel_id}")
            return True
        
        return False
    
    @abstractmethod
    async def _match(self, message_event: MessageEvent, account: Account) -> bool:
        pass
    
    async def _execute_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions_taken = []
        
        try:
            
            custom_actions = await self._custom_actions(message_event, account)
            actions_taken.extend(custom_actions)
            
        except Exception as e:
            self.logger.error(f"执行动作时出错: {e}")
            actions_taken.append(f"执行动作出错: {str(e)}")
        
        return actions_taken
    
    
    async def _custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        return []
    
    async def _log_trigger(self, message_event: MessageEvent, account: Account):
        message = message_event.message
        monitor_type = self.__class__.__name__.replace('Monitor', '')
        
        chat_info = f"聊天{message.chat_id}"
        
        sender_info = "未知发送者"
        if message.sender:
            sender_name = message.sender.full_name or "未知用户"
            if message.sender.username:
                sender_info = f"{sender_name}(@{message.sender.username})"
            else:
                sender_info = sender_name
        
        content_preview = ""
        if message.text:
            content_preview = message.text[:50] + "..." if len(message.text) > 50 else message.text
        
        monitor_info = await self._type_info()
        self.logger.info(f"🎯 [{monitor_type}监控器{monitor_info}] 频道:{message.chat_id} 发送者:{message.sender.id if message.sender else 'N/A'} 内容:\"{content_preview}\"")
        
        if self.logger.isEnabledFor(logging.DEBUG):
            detailed_log_parts = [
                "=" * 60,
                f"🎯 [{monitor_type}监控器] 详细信息",
                f"📱 账号: {account.account_id}",
                f"💬 聊天: {chat_info} (ID: {message.chat_id})",
                f"👤 发送者: {sender_info} (ID: {message.sender.id})",
                f"⏰ 时间: {message.timestamp}",
            ]
            
            if message.text:
                full_content = message.text[:200] + "..." if len(message.text) > 200 else message.text
                detailed_log_parts.append(f"📝 消息: \"{full_content}\"")
            
            if message.media and message.media.has_media:
                detailed_log_parts.append(f"📎 媒体: {message.media.media_type}")
                if message.media.file_name:
                    detailed_log_parts.append(f"📁 文件: {message.media.file_name}")
            
            if message.has_buttons:
                button_text = ", ".join(message.button_texts[:3])
                if len(message.button_texts) > 3:
                    button_text += f" (+{len(message.button_texts)-3}个)"
                detailed_log_parts.append(f"🔘 按钮: {button_text}")
            
            await self._extra_info(detailed_log_parts, message_event, account)
            
            execution_count = getattr(self.config, 'execution_count', 0) + 1
            max_executions = getattr(self.config, 'max_executions', None)
            if max_executions:
                detailed_log_parts.append(f"📊 执行: {execution_count}/{max_executions} 次")
            else:
                detailed_log_parts.append(f"📊 执行: 第 {execution_count} 次")
            
            detailed_log_parts.append("=" * 60)
            self.logger.debug("\n" + "\n".join(detailed_log_parts))
    
    async def _extra_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        pass
    
    def _log_result(self, message_event: MessageEvent, account: Account, actions_taken: List[str]):
        monitor_type = self.__class__.__name__.replace('Monitor', '')
        
        if actions_taken:
            actions_summary = ", ".join(actions_taken)
            self.logger.debug(f"✅ [{monitor_type}监控器] 执行完成: {actions_summary}")
        else:
            self.logger.debug(f"ℹ️ [{monitor_type}监控器] 匹配成功但无需执行动作")
    
    def get_config(self) -> BaseMonitorConfig:
        return self.config
    
    def update_config(self, config: BaseMonitorConfig):
        self.config = config
    
    async def _type_info(self) -> str:
        return "" 