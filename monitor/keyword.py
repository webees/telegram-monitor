"""
关键词监控器
实现关键词匹配策略
"""

import re
import asyncio
import random
from typing import List

from core.model import MessageEvent, Account
from core.model import KeywordConfig, MatchType
from .base import BaseMonitor


class KeywordMonitor(BaseMonitor):
    
    def __init__(self, config: KeywordConfig):
        super().__init__(config)
        self.keyword_config = config
        self._compiled_regex = None
        if config.match_type == MatchType.REGEX:
            try:
                self._compiled_regex = re.compile(config.keyword, re.IGNORECASE)
            except re.error as e:
                self.logger.error(f"正则表达式编译失败: {e}")
        
        self._lower_keyword = config.keyword.lower()
    
    async def _match(self, message_event: MessageEvent, account: Account) -> bool:
        message = message_event.message
        
        if not message.text:
            return False
            
        text = message.text_lower
        matched = False
        matched_content = None
        
        if self.keyword_config.match_type == MatchType.EXACT:
            matched = text == self._lower_keyword
            if matched:
                matched_content = self.keyword_config.keyword
        elif self.keyword_config.match_type == MatchType.PARTIAL:
            matched = self._lower_keyword in text
            if matched:
                matched_content = self.keyword_config.keyword
        elif self.keyword_config.match_type == MatchType.REGEX:
            if self._compiled_regex:
                search_result = self._compiled_regex.search(message.text)
                if search_result:
                    matched = True
                    matched_content = search_result.group(0)
            else:
                try:
                    pattern = re.compile(self.keyword_config.keyword, re.IGNORECASE)
                    search_result = pattern.search(message.text)
                    if search_result:
                        matched = True
                        matched_content = search_result.group(0)
                except re.error as e:
                    self.logger.error(f"正则表达式错误: {e}")
                    return False
        
        if matched and matched_content:
            self.keyword_config.matched_keyword = matched_content
        
        return matched
    
    async def _custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions_taken = []
        
        if (self.keyword_config.match_type == MatchType.REGEX and 
            self.keyword_config.regex_send_target_id):
            await self._regex_send(message_event, account)
            actions_taken.append("处理正则匹配结果")
        
        return actions_taken
    
    async def _regex_send(self, message_event: MessageEvent, account: Account):
        try:
            if self.keyword_config.regex_send_random_offset > 0:
                delay = random.uniform(0, self.keyword_config.regex_send_random_offset)
                await asyncio.sleep(delay)
            
            pattern = re.compile(self.keyword_config.keyword, re.IGNORECASE)
            matches = pattern.findall(message_event.message.text)
            
            if matches:
                match_text = '\n'.join(matches)
                client = account.client
                target_id = self.keyword_config.regex_send_target_id
                
                sent_message = await client.send_message(target_id, match_text)
                
                if self.keyword_config.regex_send_delete:
                    await asyncio.sleep(5)
                    await client.delete_messages(target_id, sent_message.id)
                
                self.logger.info(f"发送正则匹配结果到 {target_id}: {match_text}")
        
        except Exception as e:
            self.logger.error(f"处理正则匹配发送失败: {e}")

    def reply_content(self) -> List[str]:
        reply_content_type = 'custom'
        
        if hasattr(self.keyword_config, 'reply_content_type'):
            if hasattr(self.keyword_config.reply_content_type, 'value'):
                reply_content_type = self.keyword_config.reply_content_type.value
            elif isinstance(self.keyword_config.reply_content_type, str):
                reply_content_type = self.keyword_config.reply_content_type
        
        self.logger.debug(f"关键词监控器回复内容类型: {reply_content_type}")
        
        if reply_content_type == 'ai':
            if hasattr(self.keyword_config, 'ai_reply_prompt') and self.keyword_config.ai_reply_prompt:
                self.logger.info("关键词监控器使用AI回复模式")
                return []
        
        if self.keyword_config.reply_texts:
            self.logger.debug(f"关键词监控器使用自定义回复: {len(self.keyword_config.reply_texts)}条")
            return self.keyword_config.reply_texts
        
        if self.keyword_config.matched_keyword:
            self.logger.debug(f"关键词监控器使用关键词回复: {self.keyword_config.matched_keyword}")
            return [self.keyword_config.matched_keyword]
        
        self.logger.debug("关键词监控器无可用的回复内容")
        return []
    
    async def _extra_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        match_type_name = {
            'exact': '精确匹配',
            'partial': '包含匹配', 
            'regex': '正则匹配'
        }.get(self.keyword_config.match_type.value, self.keyword_config.match_type.value)
        
        log_parts.append(f"🔍 关键词: \"{self.keyword_config.keyword}\"")
        log_parts.append(f"📋 匹配类型: {match_type_name}")
        
        if hasattr(self.keyword_config, 'matched_keyword') and self.keyword_config.matched_keyword:
            log_parts.append(f"✅ 匹配内容: \"{self.keyword_config.matched_keyword}\"")
        
        if self.keyword_config.reply_enabled and self.keyword_config.reply_texts:
            reply_count = len(self.keyword_config.reply_texts)
            log_parts.append(f"💬 自动回复: 已配置 {reply_count} 条回复内容")
        
        if self.keyword_config.match_type.value == 'regex':
            if self.keyword_config.regex_send_target_id:
                log_parts.append(f"📤 正则发送目标: {self.keyword_config.regex_send_target_id}")
            if self.keyword_config.regex_send_random_offset > 0:
                log_parts.append(f"⏱️ 随机延时: 0-{self.keyword_config.regex_send_random_offset}秒")
    
    async def _type_info(self) -> str:
        match_type_name = {
            'exact': '精确',
            'partial': '包含', 
            'regex': '正则'
        }.get(self.keyword_config.match_type.value, '')
        
        return f"({match_type_name}:\"{self.keyword_config.keyword}\")"


class KeywordMatchStrategy:
    
    @staticmethod
    def exact_match(text: str, keyword: str) -> bool:
        return text.lower().strip() == keyword.lower().strip()
    
    @staticmethod
    def partial_match(text: str, keyword: str) -> bool:
        return keyword.lower() in text.lower()
    
    @staticmethod
    def regex_match(text: str, pattern: str) -> bool:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            return bool(regex.search(text))
        except re.error:
            return False
    
    @classmethod
    def get_match_function(cls, match_type: MatchType):
        strategies = {
            MatchType.EXACT: cls.exact_match,
            MatchType.PARTIAL: cls.partial_match,
            MatchType.REGEX: cls.regex_match
        }
        return strategies.get(match_type, cls.partial_match) 