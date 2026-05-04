"""
增强转发服务
默认复制消息以避免显示“转发自”，增强模式下复制失败时下载文件到本地再重新发送
"""

import os
import asyncio
import shutil
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatForwardsRestrictedError, MediaEmptyError
from telethon.tl.types import MessageEntityMention, MessageEntityUrl

from .model import TelegramMessage, Account, is_enabled
from .singleton import Singleton
from .log import get_logger


class RewriteUnavailable(Exception):
    """Raised when smart rewrite is required but cannot produce safe text."""


class EnhancedForwardService(metaclass=Singleton):
    ALBUM_LOOKUP_WINDOW = 10
    URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
    MENTION_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{5,32}\b")
    URL_TRAILING_PUNCTUATION = ".,;:!?)，。！？；：）】》」』"
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.temp_downloads: Dict[str, str] = {}
        self.last_error = ""
        
    async def forward_message_enhanced(
        self,
        message: TelegramMessage,
        account: Account,
        target_ids: List[int],
        max_download_size_mb: Optional[float] = None,
        download_folder: str = "data/dl",
        rewrite_options: Optional[Dict[str, str]] = None
    ) -> Dict[int, bool]:
        results = {}
        client = account.client
        
        for target_id in target_ids:
            self.last_error = ""
            try:
                success = await self.copy_message_without_source(
                    client, message, target_id, rewrite_options, raise_on_rewrite_failure=True
                )
                if success:
                    results[target_id] = True
                    self.logger.info(f"无来源标记复制成功到 {target_id}")
                    continue
                
                success = await self._download_resend(
                    client, message, target_id, max_download_size_mb, download_folder, rewrite_options
                )
                results[target_id] = success
                
            except RewriteUnavailable as e:
                self.last_error = f"智能追加失败，已阻止原文转发: {e}"
                self.logger.error(f"转发到 {target_id} 时阻止原文转发: {e}")
                results[target_id] = False
            except Exception as e:
                self.last_error = str(e)
                self.logger.error(f"转发到 {target_id} 时出错: {e}")
                results[target_id] = False
        
        return results
    
    async def copy_message_without_source(
        self, 
        client: TelegramClient, 
        message: TelegramMessage, 
        target_id: int,
        rewrite_options: Optional[Dict[str, str]] = None,
        raise_on_rewrite_failure: bool = False
    ) -> bool:
        self.last_error = ""
        try:
            original_message = await client.get_messages(message.chat_id, ids=message.message_id)
            if not original_message:
                self.logger.error(f"找不到原始消息: chat={message.chat_id}, message={message.message_id}")
                return False

            if message.grouped_id or getattr(original_message, 'grouped_id', None):
                album_messages = await self._get_album_messages(client, message, original_message)
                if len(album_messages) > 1:
                    await self._send_album_without_source(client, target_id, album_messages, rewrite_options)
                    self.logger.info(f"无来源标记复制媒体组到 {target_id}: {len(album_messages)} 条")
                    return True

            rewritten_text = await self._rewrite_text_if_enabled(message.text, rewrite_options)
            if rewritten_text is not None:
                if getattr(original_message, 'media', None):
                    await self._send_file(client, target_id, original_message.media, caption=rewritten_text)
                else:
                    await self._send_message(client, target_id, rewritten_text)
                    self.logger.info(f"智能追加后复制消息到 {target_id}")
                return True

            await client.send_message(target_id, original_message)
            return True
            
        except RewriteUnavailable as e:
            self.last_error = f"智能追加失败，已阻止原文转发: {e}"
            self.logger.error(f"智能追加失败，跳过转发到 {target_id}: {e}")
            if raise_on_rewrite_failure:
                raise
            return False
        except (ChatForwardsRestrictedError, MediaEmptyError) as e:
            self.last_error = str(e)
            self.logger.info(f"复制消息到 {target_id} 受限制: {e}")
            return False
        except FloodWaitError as e:
            self.last_error = f"频率限制，等待 {e.seconds} 秒"
            self.logger.warning(f"复制消息频率限制，等待 {e.seconds} 秒")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            self.last_error = str(e)
            self.logger.error(f"复制消息失败: {e}")
            return False

    async def _get_album_messages(self, client: TelegramClient, message: TelegramMessage, original_message) -> List:
        grouped_id = message.grouped_id or getattr(original_message, 'grouped_id', None)
        if not grouped_id:
            return [original_message]

        min_id = max(0, message.message_id - self.ALBUM_LOOKUP_WINDOW)
        max_id = message.message_id + self.ALBUM_LOOKUP_WINDOW
        try:
            nearby_messages = await client.get_messages(
                message.chat_id,
                limit=self.ALBUM_LOOKUP_WINDOW * 2 + 1,
                min_id=min_id,
                max_id=max_id
            )
        except TypeError:
            nearby_messages = await client.get_messages(message.chat_id, limit=self.ALBUM_LOOKUP_WINDOW * 2)

        by_id = {}
        for item in [*(nearby_messages or []), original_message]:
            if getattr(item, 'grouped_id', None) == grouped_id and getattr(item, 'media', None):
                by_id[getattr(item, 'id', id(item))] = item

        return sorted(by_id.values(), key=lambda item: getattr(item, 'id', 0))

    async def _send_album_without_source(
        self,
        client: TelegramClient,
        target_id: int,
        album_messages: List,
        rewrite_options: Optional[Dict[str, str]] = None
    ):
        files = [item.media for item in album_messages if getattr(item, 'media', None)]
        captions = [getattr(item, 'message', '') or '' for item in album_messages]
        if not files:
            raise ValueError("媒体组中没有可发送的媒体")

        first_caption = next((caption for caption in captions if caption), "")
        rewritten_text = await self._rewrite_text_if_enabled(first_caption, rewrite_options)
        if rewritten_text is not None:
            captions = [rewritten_text] + [""] * (len(files) - 1)

        await self._send_file(client, target_id, files, caption=captions)

    async def _rewrite_text_if_enabled(self, text: str, rewrite_options: Optional[Dict[str, str]] = None) -> Optional[str]:
        rewrite_options = rewrite_options or {}
        if not is_enabled(rewrite_options.get("enabled")) or not text or not text.strip():
            return None

        try:
            from .ai import AIService

            ai_service = AIService()
            result = await ai_service.rewrite_forward_text(
                text=text,
                append_template=rewrite_options.get("template", ""),
                custom_prompt=rewrite_options.get("prompt", "")
            )
            if result and result.get("final_text"):
                self.logger.info(f"转发智能追加完成，主题: {result.get('topic', '未知')}")
                return result["final_text"]
            raise RewriteUnavailable("AI未返回有效主题内容")
        except Exception as e:
            if isinstance(e, RewriteUnavailable):
                raise
            raise RewriteUnavailable(str(e)) from e
    
    async def _download_resend(
        self,
        client: TelegramClient,
        message: TelegramMessage,
        target_id: int,
        max_download_size_mb: Optional[float],
        download_folder: str,
        rewrite_options: Optional[Dict[str, str]] = None
    ) -> bool:
        try:
            if message.media and message.media.file_size_mb:
                if max_download_size_mb and message.media.file_size_mb > max_download_size_mb:
                    self.logger.warning(
                        f"文件大小 {message.media.file_size_mb:.2f}MB 超过限制 {max_download_size_mb}MB"
                    )
                    return False
            
            download_path = Path(download_folder)
            download_path.mkdir(parents=True, exist_ok=True)
            
            if message.media and message.media.has_media:
                return await self._send_media(client, message, target_id, download_path, rewrite_options)
            else:
                return await self._send_text(client, message, target_id, rewrite_options)
                
        except Exception as e:
            self.last_error = str(e)
            self.logger.error(f"下载重发失败: {e}")
            return False
    
    async def _send_media(
        self,
        client: TelegramClient,
        message: TelegramMessage,
        target_id: int,
        download_path: Path,
        rewrite_options: Optional[Dict[str, str]] = None
    ) -> bool:
        downloaded_path = None
        try:
            original_message = await client.get_messages(message.chat_id, ids=message.message_id)
            
            if not original_message or not original_message.media:
                return False

            caption = await self._rewrite_text_if_enabled(message.text, rewrite_options)
            if caption is None:
                caption = message.text or None
            
            file_name = message.media.file_name or f"file_{message.message_id}"
            file_path = download_path / file_name
            
            self.logger.info(f"开始下载文件: {file_name}")
            downloaded_path = await original_message.download_media(file=str(file_path))
            
            if not downloaded_path:
                self.logger.error("文件下载失败")
                return False
            
            await self._send_file(client, target_id, downloaded_path, caption=caption)
            
            self.logger.info(f"文件重发成功到 {target_id}: {file_name}")
            return True
            
        except RewriteUnavailable as e:
            self.last_error = f"智能追加失败，已阻止原文转发: {e}"
            self.logger.error(f"下载媒体文件前智能追加失败: {e}")
            return False
        except Exception as e:
            self.last_error = str(e)
            self.logger.error(f"下载媒体文件失败: {e}")
            return False
        finally:
            if downloaded_path:
                await self._cleanup_file(downloaded_path)
    
    async def _send_text(
        self,
        client: TelegramClient,
        message: TelegramMessage,
        target_id: int,
        rewrite_options: Optional[Dict[str, str]] = None
    ) -> bool:
        try:
            if message.text:
                text = await self._rewrite_text_if_enabled(message.text, rewrite_options)
                if text is None:
                    text = message.text
                await self._send_message(client, target_id, text)
                self.logger.info(f"文本消息重发成功到 {target_id}")
                return True
            return False
            
        except RewriteUnavailable as e:
            self.last_error = f"智能追加失败，已阻止原文转发: {e}"
            self.logger.error(f"发送文本前智能追加失败: {e}")
            return False
        except Exception as e:
            self.last_error = str(e)
            self.logger.error(f"发送文本消息失败: {e}")
            return False
    
    async def _cleanup_file(self, file_path: str):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.debug(f"已清理临时文件: {file_path}")
        except Exception as e:
            self.logger.warning(f"清理临时文件失败: {e}")
    
    async def cleanup_all_temp_files(self):
        for file_path in self.temp_downloads.values():
            await self._cleanup_file(file_path)
        self.temp_downloads.clear()
        self.logger.info("已清理所有临时文件")
    
    def get_download_statistics(self) -> Dict[str, Any]:
        return {
            "temp_files_count": len(self.temp_downloads),
            "temp_files": list(self.temp_downloads.keys())
        }

    async def _send_message(self, client: TelegramClient, target_id: int, text: str):
        entities = self._clickable_entities(text)
        if entities:
            await client.send_message(target_id, text, formatting_entities=entities)
            return
        await client.send_message(target_id, text)

    async def _send_file(self, client: TelegramClient, target_id: int, files, caption=None):
        entities = self._caption_entities(caption)
        if entities:
            await client.send_file(target_id, files, caption=caption, formatting_entities=entities)
            return
        await client.send_file(target_id, files, caption=caption)

    def _caption_entities(self, caption):
        if isinstance(caption, list):
            entities = [self._clickable_entities(item) or [] for item in caption]
            return entities if any(entities) else None
        return self._clickable_entities(caption)

    def _clickable_entities(self, text: Optional[str]):
        if not text:
            return None

        spans = []
        for match in self.URL_RE.finditer(text):
            start, end = match.span()
            while end > start and text[end - 1] in self.URL_TRAILING_PUNCTUATION:
                end -= 1
            if end > start:
                spans.append((start, end, MessageEntityUrl))

        for match in self.MENTION_RE.finditer(text):
            start, end = match.span()
            if not any(start < span_end and end > span_start for span_start, span_end, _ in spans):
                spans.append((start, end, MessageEntityMention))

        if not spans:
            return None

        return [
            entity(offset=self._utf16_length(text[:start]), length=self._utf16_length(text[start:end]))
            for start, end, entity in sorted(spans, key=lambda item: (item[0], item[1]))
        ]

    @staticmethod
    def _utf16_length(text: str) -> int:
        return len(text.encode("utf-16-le")) // 2
