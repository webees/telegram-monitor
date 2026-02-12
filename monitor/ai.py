"""
AI监控器
通过AI判断消息是否符合用户自定义的监控条件
"""

import re
from typing import List

from core.model import MessageEvent, Account
from core.model import AIMonitorConfig
from core.ai import AIService
from .base import BaseMonitor
from core.log import get_logger


class AIMonitor(BaseMonitor):
    
    def __init__(self, config: AIMonitorConfig):
        super().__init__(config)
        self.ai_config = config
        self.ai_service = AIService()
        self.logger = get_logger(__name__)
    
    async def _match(self, message_event: MessageEvent, account: Account) -> bool:
        message = message_event.message
        
        if not self.ai_service.is_configured():
            self.logger.error("AI服务未配置，无法进行AI监控")
            return False
        
        ai_prompt = self._build_ai_prompt(message)
        
        ai_response = await self.ai_service.get_chat_completion([
            {"role": "user", "content": ai_prompt}
        ])
        
        if not ai_response:
            self.logger.warning("AI服务返回空结果")
            return False
        
        self.ai_config.ai_response_content = ai_response
        self.logger.debug(f"保存AI返回内容: {ai_response[:100]}...")
        
        return self._parse_ai_response(ai_response)
    
    def _build_ai_prompt(self, message) -> str:
        prompt_parts = [
            f"用户提示词: {self.ai_config.ai_prompt}",
            "",
            "请根据上述提示词判断以下消息是否符合条件:",
            f"消息内容: {message.text}",
        ]
        
        if message.sender:
            prompt_parts.append(f"发送者: {message.sender.full_name}")
            if message.sender.username:
                prompt_parts.append(f"用户名: @{message.sender.username}")
        
        if message.media and message.media.has_media:
            prompt_parts.append(f"包含媒体: {message.media.media_type}")
            if message.media.file_name:
                prompt_parts.append(f"文件名: {message.media.file_name}")
        
        if message.has_buttons:
            button_texts = ", ".join(message.button_texts)
            prompt_parts.append(f"包含按钮: {button_texts}")
        
        if message.is_forwarded:
            prompt_parts.append("这是一条转发消息")
        
        if self.ai_config.reply_enabled and not self.ai_config.reply_texts:
            prompt_parts.extend([
                "",
                "请按照以下格式回复:",
                "判断: yes/no (是否符合监控条件)",
                "回复: [如果符合条件，请生成一条合适的回复内容；如果不符合，请写'无']",
                "",
                "示例:",
                "判断: yes",
                "回复: 您好！我注意到您提到了相关内容。"
            ])
        else:
            prompt_parts.extend([
                "",
                "请仅回答 'yes' 或 'no'，表示是否符合监控条件。",
                "如果符合条件回答 yes，不符合回答 no。"
            ])
        
        return "\n".join(prompt_parts)
    
    def _parse_ai_response(self, ai_response: str) -> bool:
        if "判断:" in ai_response and "回复:" in ai_response:
            lines = ai_response.strip().split('\n')
            judgment_result = None
            reply_content = None
            
            for line in lines:
                line = line.strip()
                if line.startswith("判断:"):
                    judgment_part = line.replace("判断:", "").strip().lower()
                    judgment_result = "yes" in judgment_part or "是" in judgment_part
                elif line.startswith("回复:"):
                    reply_part = line.replace("回复:", "").strip()
                    if reply_part and reply_part != "无":
                        reply_content = reply_part
            
            if reply_content:
                self.ai_config.ai_response_content = reply_content
                self.logger.info(f"AI生成回复内容: {reply_content}")
            
            if judgment_result is not None:
                self.logger.info(f"AI判断结果: {'匹配' if judgment_result else '不匹配'}")
                return judgment_result
        
        response = ai_response.lower().strip()
        
        response = re.sub(r'[^\w\s]', '', response)
        
        positive_keywords = ['yes', 'y', '是', '符合', '匹配', 'true', '1', 'match']
        negative_keywords = ['no', 'n', '否', '不符合', '不匹配', 'false', '0', 'nomatch']
        
        for keyword in positive_keywords:
            if keyword in response:
                self.logger.info(f"AI判断结果: 匹配 (关键词: {keyword})")
                return True
        
        for keyword in negative_keywords:
            if keyword in response:
                self.logger.info(f"AI判断结果: 不匹配 (关键词: {keyword})")
                return False
        
        self.logger.warning(f"AI回复不明确: {ai_response}，默认为不匹配")
        return False
    
    async def _custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions_taken = []
        
        actions_taken.append("AI判断匹配成功")
        
        self.logger.info(
            f"AI监控匹配: 聊天={message_event.message.chat_id}, "
            f"发送者={message_event.message.sender.full_name}, "
            f"提示词='{self.ai_config.ai_prompt[:50]}...'"
        )
        
        return actions_taken

    def reply_content(self) -> List[str]:
        if self.ai_config.reply_texts:
            return self.ai_config.reply_texts
        
        if self.ai_config.ai_response_content:
            cleaned_content = self._clean_reply(self.ai_config.ai_response_content)
            if cleaned_content:
                return [cleaned_content]
        
        return []
    
    def _clean_reply(self, ai_response: str) -> str:
        if not ai_response:
            return ""
        
        if not any(keyword in ai_response.lower() for keyword in ['yes', 'no', '是', '否', 'true', 'false']):
            return ai_response.strip()
        
        response = ai_response.strip()
        
        simple_responses = ['yes', 'no', 'y', 'n', '是', '否', 'true', 'false', '1', '0']
        if response.lower().strip() in simple_responses:
            return ""
        
        prefixes_to_remove = [
            "yes,", "no,", "是,", "否,", "符合,", "不符合,", "匹配,", "不匹配,"
        ]
        
        for prefix in prefixes_to_remove:
            if response.lower().startswith(prefix.lower()):
                response = response[len(prefix):].strip()
                break
        
        if len(response.strip()) < 1:
            return ""
        
        return response

    async def _extra_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        log_parts.append(f"🤖 AI模型: {self.ai_config.ai_model}")
        log_parts.append(f"🎨 提示词: \"{self.ai_config.ai_prompt[:80]}{'...' if len(self.ai_config.ai_prompt) > 80 else ''}\"")
        log_parts.append(f"📊 置信度阈值: {self.ai_config.confidence_threshold}")
        
        if hasattr(self.ai_config, 'ai_response_content') and self.ai_config.ai_response_content:
            ai_response_preview = self.ai_config.ai_response_content[:50]
            if len(self.ai_config.ai_response_content) > 50:
                ai_response_preview += "..."
            log_parts.append(f"🧠 AI判断结果: \"{ai_response_preview}\"")
        
        if self.ai_config.reply_enabled:
            if self.ai_config.reply_texts:
                reply_count = len(self.ai_config.reply_texts)
                log_parts.append(f"💬 自动回复: 已配置 {reply_count} 条固定回复")
            else:
                log_parts.append(f"💬 自动回复: 使用AI动态生成回复")
            
            if self.ai_config.reply_delay_max > 0:
                log_parts.append(f"⏱️ 回复延时: {self.ai_config.reply_delay_min}-{self.ai_config.reply_delay_max}秒")
    
    async def _type_info(self) -> str:
        prompt_preview = self.ai_config.ai_prompt[:30] + "..." if len(self.ai_config.ai_prompt) > 30 else self.ai_config.ai_prompt
        ai_response_preview = ""
        
        if hasattr(self.ai_config, 'ai_response_content') and self.ai_config.ai_response_content:
            ai_response_preview = f" AI回复:\"{self.ai_config.ai_response_content[:20]}{'...' if len(self.ai_config.ai_response_content) > 20 else ''}\""
        
        return f"(AI:\"{prompt_preview}\"{ai_response_preview})"


class AIMonitorBuilder:
    
    def __init__(self):
        self.config = AIMonitorConfig()
    
    def with_prompt(self, prompt: str):
        self.config.ai_prompt = prompt
        return self
    
    def with_chats(self, chat_ids: List[int]):
        self.config.chats = chat_ids
        return self
    
    def with_email_notify(self, enabled: bool = True):
        self.config.email_notify = enabled
        return self
    
    def with_auto_forward(self, enabled: bool = True, targets: List[int] = None):
        self.config.auto_forward = enabled
        if targets:
            self.config.forward_targets = targets
        return self
    
    def with_enhanced_forward(self, enabled: bool = True, max_size_mb: float = None):
        self.config.enhanced_forward = enabled
        if max_size_mb:
            self.config.max_download_size_mb = max_size_mb
        return self
    
    def with_confidence_threshold(self, threshold: float):
        self.config.confidence_threshold = threshold
        return self
    
    def with_max_executions(self, max_executions: int):
        self.config.max_executions = max_executions
        return self
    
    def with_reply(self, enabled: bool = True, reply_texts: List[str] = None, 
                   reply_delay_min: float = 0, reply_delay_max: float = 0, 
                   reply_mode: str = 'reply'):
        self.config.reply_enabled = enabled
        if reply_texts:
            self.config.reply_texts = reply_texts
        self.config.reply_delay_min = reply_delay_min
        self.config.reply_delay_max = reply_delay_max
        self.config.reply_mode = reply_mode
        return self
    
    def with_priority(self, priority: int):
        self.config.priority = priority
        return self
    
    def with_execution_mode(self, execution_mode: str):
        self.config.execution_mode = execution_mode
        return self
    
    def build(self) -> AIMonitor:
        return AIMonitor(self.config) 