"""
按钮监控器
实现按钮点击监控策略
"""

from typing import List

from core.model import MessageEvent, Account
from core.model import ButtonConfig, MonitorMode
from .base import BaseMonitor


class ButtonMonitor(BaseMonitor):

    def __init__(self, config: ButtonConfig):
        super().__init__(config)
        self.button_config = config

    async def _match(self, message_event: MessageEvent, account: Account) -> bool:
        message = message_event.message

        if not message.has_buttons:
            return False

        if self.button_config.mode == MonitorMode.MANUAL:
            return self._manual_match(message)
        elif self.button_config.mode == MonitorMode.AI:
            return True

        return False

    def _manual_match(self, message) -> bool:
        keyword = self.button_config.button_keyword.lower()
        for button_text in message.button_texts:
            if keyword in button_text.lower():
                return True
        return False

    async def _custom_actions(self, message_event: MessageEvent, account: Account) -> List[str]:
        actions_taken = []

        if self.button_config.mode == MonitorMode.MANUAL:
            clicked = await self._click_manual_button(message_event, account)
            if clicked:
                actions_taken.append("点击按钮（手动模式）")
        elif self.button_config.mode == MonitorMode.AI:
            clicked = await self._click_ai_button(message_event, account)
            if clicked:
                actions_taken.append("点击按钮（AI模式）")

        return actions_taken

    async def _click_manual_button(self, message_event: MessageEvent, account: Account) -> bool:
        try:
            message = message_event.message
            keyword = self.button_config.button_keyword.lower()

            target_button = message.get_button_by_text(keyword, exact_match=False)

            if target_button:
                try:
                    client = account.client
                    original_msg = await client.get_messages(message.chat_id, ids=message.message_id)

                    if original_msg and original_msg.buttons:
                        await original_msg.click(target_button.row, target_button.col)
                        self.logger.info(f"✅ 点击按钮成功: {target_button.text} (位置: 行{target_button.row}, 列{target_button.col})")
                        return True
                    else:
                        self.logger.error("无法获取原始消息对象或按钮不存在")
                        return False
                except Exception as click_error:
                    self.logger.error(f"点击按钮失败: {click_error}")
                    return False
            else:
                self.logger.debug(f"未找到包含关键词 '{keyword}' 的按钮")

        except Exception as e:
            self.logger.error(f"点击按钮失败: {e}")

        return False

    async def _click_ai_button(self, message_event: MessageEvent, account: Account) -> bool:
        try:
            message = message_event.message

            prompt = self.button_config.ai_prompt or "请根据消息内容选择最合适的按钮"
            buttons_text = "\n".join(message.button_texts)
            full_prompt = f"{prompt}\n消息内容: {message.text}\n按钮选项:\n{buttons_text}"

            from core.ai import AIService
            ai_service = AIService()

            if not ai_service.is_configured():
                self.logger.error("AI服务未配置，无法使用AI模式")
                return False

            try:
                ai_choice = await ai_service.analyze_button_choice(
                    message_text=message.text or "",
                    button_options=message.button_texts,
                    custom_prompt=prompt
                )

                if ai_choice:
                    self.logger.info(f"AI选择按钮: {ai_choice}")

                    target_button = message.get_button_by_text(ai_choice, exact_match=False)
                    if target_button:
                        client = account.client
                        original_msg = await client.get_messages(message.chat_id, ids=message.message_id)

                        if original_msg and original_msg.buttons:
                            await original_msg.click(target_button.row, target_button.col)
                            self.logger.info(f"✅ AI选择并点击按钮成功: {target_button.text} (位置: 行{target_button.row}, 列{target_button.col})")
                            return True
                        else:
                            self.logger.error("无法获取原始消息对象或按钮不存在")
                            return False
                    else:
                        self.logger.warning(f"未找到AI推荐的按钮: {ai_choice}")
                        return False
                else:
                    self.logger.warning("AI未返回有效的按钮选择")
                    return False

            except Exception as ai_error:
                self.logger.error(f"AI分析按钮失败: {ai_error}")
                return False

        except Exception as e:
            self.logger.error(f"AI模式点击按钮失败: {e}")

        return False

    async def _get_ai_choice(self, prompt: str) -> str:
        return ""

    async def _extra_info(self, log_parts: List[str], message_event: MessageEvent, account: Account):
        message = message_event.message

        mode_name = {
            'manual': '手动模式',
            'ai': 'AI模式'
        }.get(self.button_config.mode.value, self.button_config.mode.value)

        log_parts.append(f"🔘 监控模式: {mode_name}")

        if self.button_config.mode.value == 'manual':
            log_parts.append(f"🔍 目标按钮: \"{self.button_config.button_keyword}\"")
        elif self.button_config.mode.value == 'ai':
            log_parts.append(f"🤖 AI提示: \"{self.button_config.ai_prompt[:60]}{'...' if len(self.button_config.ai_prompt) > 60 else ''}\"")

        if message.has_buttons:
            button_count = len(message.button_texts)
            button_preview = ", ".join(message.button_texts[:3])
            if button_count > 3:
                button_preview += f" (+{button_count-3}个)"
            log_parts.append(f"🎯 检测到按钮: {button_preview}")
            log_parts.append(f"📊 按钮总数: {button_count} 个")

    async def _type_info(self) -> str:
        mode_name = {
            'manual': '手动',
            'ai': 'AI'
        }.get(self.button_config.mode.value, '')
        
        if self.button_config.mode.value == 'manual':
            return f"({mode_name}:\"{self.button_config.button_keyword}\")"
        else:
            prompt_preview = self.button_config.ai_prompt[:25] + "..." if len(self.button_config.ai_prompt) > 25 else self.button_config.ai_prompt
            return f"({mode_name}:\"{prompt_preview}\")" 
