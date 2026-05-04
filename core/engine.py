"""
监控引擎 - 应用观察者模式
负责协调各种监控器和处理消息事件
"""

import asyncio
import pytz
import copy
from collections import deque
from pathlib import Path
from typing import List, Dict, Set, Optional
from datetime import datetime
from threading import Lock
from telethon import events
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .model import MessageEvent, TelegramMessage, MessageSender, Account
from monitor import BaseMonitor, MonitorResult, monitor_factory
from .singleton import Singleton
from .log import get_logger
from .storage import atomic_write_json, read_json_file


class MonitorEngine(metaclass=Singleton):
    ALBUM_GATHER_DELAY_SECONDS = 1.0

    def __init__(self):
        self.monitors: Dict[str, List[BaseMonitor]] = {}
        self.processed_messages: deque = deque(maxlen=5000)
        self.processed_messages_set: set = set()
        self.scheduled_messages: List[Dict] = []
        self.logger = get_logger(__name__)
        self.monitors_file = Path("data/monitor.json")
        self.scheduled_messages_file = Path("data/schedule.json")
        self._save_lock = Lock()

        self.scheduler = None
        self._scheduler_started = False

        self._load_monitors()
        self._load_scheduled()

    def _start_scheduler(self):
        if not self._scheduler_started:
            try:
                loop = asyncio.get_running_loop()
                if not self.scheduler:
                    self.scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Shanghai'))

                if not self.scheduler.running:
                    self.scheduler.start()
                    self.logger.info("调度器已启动")

                self._scheduler_started = True

                self._restore_jobs()

            except RuntimeError:
                self.logger.debug("事件循环尚未启动，调度器将延后启动")

    def _restore_jobs(self):
        if not self.scheduler or not self.scheduler.running:
            return

        restored_count = 0
        for message in self.scheduled_messages:
            job_id = message.get('job_id')
            cron_expr = message.get('cron', message.get('schedule'))
            active = message.get('active', True)
            schedule_mode = message.get('schedule_mode', 'cron')

            if job_id and cron_expr and active:
                try:
                    if schedule_mode == 'interval':
                        parts = cron_expr.split()
                        hours = int(parts[0]) if len(parts) > 0 else 0
                        minutes = int(parts[1]) if len(parts) > 1 else 0

                        trigger = IntervalTrigger(
                            hours=hours,
                            minutes=minutes,
                            timezone=pytz.timezone('Asia/Shanghai')
                        )
                        self.logger.debug(f"恢复间隔任务 {job_id}: {hours}小时 {minutes}分钟")
                    else:
                        trigger = CronTrigger.from_crontab(cron_expr, timezone=pytz.timezone('Asia/Shanghai'))
                        self.logger.debug(f"恢复Cron任务 {job_id}: {cron_expr}")

                    self.scheduler.add_job(
                        self._run_scheduled,
                        trigger,
                        id=job_id,
                        args=[job_id],
                        replace_existing=True
                    )
                    restored_count += 1
                except Exception as scheduler_error:
                    self.logger.error(f"恢复调度任务失败 {job_id}: {scheduler_error}")

        if restored_count > 0:
            self.logger.info(f"恢复 {restored_count} 个调度任务")

    def _load_monitors(self):
        old_config_file = Path("data/monitor.bak")
        if old_config_file.exists():
            self.logger.warning("检测到旧版本的monitor.bak文件，正在尝试删除...")
            try:
                old_config_file.unlink()
                self.logger.info("已删除旧版本的monitor.bak文件")
            except Exception as e:
                self.logger.error(f"删除旧版本monitor.bak文件失败: {e}")
                self.logger.warning("建议手动删除data/monitor.bak文件后重新启动程序")
                return

        if not self.monitors_file.exists():
            self.logger.info("监控器配置文件不存在，跳过加载")
            return

        try:
            data = read_json_file(self.monitors_file, {})

            for account_id, monitors_data in data.items():
                for monitor_data in monitors_data:
                    try:
                        monitor_type = monitor_data.get('type')
                        config_data = monitor_data.get('config', {})

                        if monitor_type == 'keyword':
                            from .model import KeywordConfig, MatchType
                            config = KeywordConfig(
                                keyword=config_data.get('keyword', ''),
                                match_type=MatchType(config_data.get('match_type', 'partial')),
                                chats=config_data.get('chats', []),
                                users=config_data.get('users', []),
                                blocked_users=config_data.get('blocked_users', []),
                                blocked_channels=config_data.get('blocked_channels', []),
                                blocked_bots=config_data.get('blocked_bots', []),
                                bot_ids=config_data.get('bot_ids', []),
                                channel_ids=config_data.get('channel_ids', []),
                                group_ids=config_data.get('group_ids', []),
                                email_notify=config_data.get('email_notify', False),
                                auto_forward=config_data.get('auto_forward', False),
                                forward_targets=config_data.get('forward_targets', []),
                                enhanced_forward=config_data.get('enhanced_forward', False),
                                forward_rewrite_enabled=config_data.get('forward_rewrite_enabled', False),
                                forward_rewrite_template=config_data.get('forward_rewrite_template', ''),
                                forward_rewrite_prompt=config_data.get('forward_rewrite_prompt', ''),
                                reply_enabled=config_data.get('reply_enabled', False),
                                reply_texts=config_data.get('reply_texts', []),
                                reply_delay_min=config_data.get('reply_delay_min', 0),
                                reply_delay_max=config_data.get('reply_delay_max', 5),
                                reply_mode=config_data.get('reply_mode', 'reply'),
                                max_executions=config_data.get('max_executions'),
                                priority=config_data.get('priority', 50),
                                execution_mode=config_data.get('execution_mode', 'merge'),
                                log_file=config_data.get('log_file')
                            )
                            monitor = monitor_factory.create_monitor(config)
                            if monitor:
                                self.add_monitor(account_id, monitor)

                        elif monitor_type == 'file':
                            from .model import FileConfig
                            config = FileConfig(
                                file_extension=config_data.get('file_extension', ''),
                                chats=config_data.get('chats', []),
                                users=config_data.get('users', []),
                                blocked_users=config_data.get('blocked_users', []),
                                blocked_channels=config_data.get('blocked_channels', []),
                                blocked_bots=config_data.get('blocked_bots', []),
                                bot_ids=config_data.get('bot_ids', []),
                                channel_ids=config_data.get('channel_ids', []),
                                group_ids=config_data.get('group_ids', []),
                                save_folder=config_data.get('save_folder'),
                                min_size=config_data.get('min_size'),
                                max_size=config_data.get('max_size'),
                                email_notify=config_data.get('email_notify', False),
                                auto_forward=config_data.get('auto_forward', False),
                                forward_targets=config_data.get('forward_targets', []),
                                enhanced_forward=config_data.get('enhanced_forward', False),
                                max_download_size_mb=config_data.get('max_download_size_mb'),
                                forward_rewrite_enabled=config_data.get('forward_rewrite_enabled', False),
                                forward_rewrite_template=config_data.get('forward_rewrite_template', ''),
                                forward_rewrite_prompt=config_data.get('forward_rewrite_prompt', ''),
                                max_executions=config_data.get('max_executions'),
                                priority=config_data.get('priority', 50),
                                execution_mode=config_data.get('execution_mode', 'merge'),
                                log_file=config_data.get('log_file')
                            )
                            monitor = monitor_factory.create_monitor(config)
                            if monitor:
                                self.add_monitor(account_id, monitor)
                                self.logger.info(f"加载文件监控器: {config.file_extension}")

                        elif monitor_type == 'ai':
                            from .model import AIMonitorConfig
                            config = AIMonitorConfig(
                                ai_prompt=config_data.get('ai_prompt', ''),
                                confidence_threshold=config_data.get('confidence_threshold', 0.7),
                                ai_model=config_data.get('ai_model', 'gpt-4o'),
                                chats=config_data.get('chats', []),
                                users=config_data.get('users', []),
                                blocked_users=config_data.get('blocked_users', []),
                                blocked_channels=config_data.get('blocked_channels', []),
                                blocked_bots=config_data.get('blocked_bots', []),
                                bot_ids=config_data.get('bot_ids', []),
                                channel_ids=config_data.get('channel_ids', []),
                                group_ids=config_data.get('group_ids', []),
                                email_notify=config_data.get('email_notify', False),
                                auto_forward=config_data.get('auto_forward', False),
                                forward_targets=config_data.get('forward_targets', []),
                                enhanced_forward=config_data.get('enhanced_forward', False),
                                forward_rewrite_enabled=config_data.get('forward_rewrite_enabled', False),
                                forward_rewrite_template=config_data.get('forward_rewrite_template', ''),
                                forward_rewrite_prompt=config_data.get('forward_rewrite_prompt', ''),
                                reply_enabled=config_data.get('reply_enabled', False),
                                reply_texts=config_data.get('reply_texts', []),
                                reply_delay_min=config_data.get('reply_delay_min', 0),
                                reply_delay_max=config_data.get('reply_delay_max', 5),
                                reply_mode=config_data.get('reply_mode', 'reply'),
                                max_executions=config_data.get('max_executions'),
                                priority=config_data.get('priority', 50),
                                execution_mode=config_data.get('execution_mode', 'merge'),
                                log_file=config_data.get('log_file')
                            )
                            monitor = monitor_factory.create_monitor(config)
                            if monitor:
                                self.add_monitor(account_id, monitor)
                                self.logger.info(f"加载AI监控器: {config.ai_prompt[:50]}...")

                        elif monitor_type == 'allmessages' or monitor_type == 'all_messages':
                            from .model import AllMessagesConfig
                            config = AllMessagesConfig(
                                chat_id=config_data.get('chat_id', 0),
                                chats=config_data.get('chats', []),
                                users=config_data.get('users', []),
                                blocked_users=config_data.get('blocked_users', []),
                                blocked_channels=config_data.get('blocked_channels', []),
                                blocked_bots=config_data.get('blocked_bots', []),
                                bot_ids=config_data.get('bot_ids', []),
                                channel_ids=config_data.get('channel_ids', []),
                                group_ids=config_data.get('group_ids', []),
                                email_notify=config_data.get('email_notify', False),
                                auto_forward=config_data.get('auto_forward', False),
                                forward_targets=config_data.get('forward_targets', []),
                                enhanced_forward=config_data.get('enhanced_forward', False),
                                forward_rewrite_enabled=config_data.get('forward_rewrite_enabled', False),
                                forward_rewrite_template=config_data.get('forward_rewrite_template', ''),
                                forward_rewrite_prompt=config_data.get('forward_rewrite_prompt', ''),
                                reply_enabled=config_data.get('reply_enabled', False),
                                reply_texts=config_data.get('reply_texts', []),
                                reply_delay_min=config_data.get('reply_delay_min', 0),
                                reply_delay_max=config_data.get('reply_delay_max', 5),
                                reply_mode=config_data.get('reply_mode', 'reply'),
                                max_executions=config_data.get('max_executions'),
                                priority=config_data.get('priority', 50),
                                execution_mode=config_data.get('execution_mode', 'merge'),
                                log_file=config_data.get('log_file')
                            )
                            monitor = monitor_factory.create_monitor(config)
                            if monitor:
                                self.add_monitor(account_id, monitor)
                                self.logger.info(f"加载全量监控器: 聊天{config.chat_id}")

                        else:
                            self.logger.warning(f"未知的监控器类型: {monitor_type}")

                    except Exception as e:
                        self.logger.error(f"加载监控器配置失败: {e}")

        except Exception as e:
            self.logger.error(f"加载监控器文件失败: {e}")

    def _save_monitors(self):
        try:
            monitors_data = {}
            for account_id, monitors in self.monitors.items():
                monitors_data[account_id] = []
                for monitor in monitors:
                    if hasattr(monitor, 'config'):
                        config = monitor.config
                        monitor_data = {
                            'type': monitor.__class__.__name__.replace('Monitor', '').lower(),
                            'config': {}
                        }

                        for attr in dir(config):
                            if not attr.startswith('_'):
                                try:
                                    value = getattr(config, attr)
                                except Exception:
                                    continue
                                if not callable(value) and isinstance(value, (str, int, float, bool, list, dict)):
                                    monitor_data['config'][attr] = value
                                elif hasattr(value, 'value'):
                                    monitor_data['config'][attr] = value.value

                        monitors_data[account_id].append(monitor_data)

            monitors_data_copy = copy.deepcopy(monitors_data)
            atomic_write_json(self.monitors_file, monitors_data_copy, self._save_lock)

            self.logger.info(f"已保存监控器配置")

        except Exception as e:
            self.logger.error(f"序列化监控器配置失败: {e}")

    async def start(self):
        try:
            self._start_scheduler()

            from core import AccountManager
            account_manager = AccountManager()

            for account in account_manager.list_accounts():
                if account.client and account.is_connected():
                    if account.monitor_active:
                        self.setup_event_handlers(account)
                        self.logger.info(f"为账号 {account.account_id} 启动监控")
                else:
                    if await account_manager.connect_account(account.account_id):
                        if account.monitor_active:
                            self.setup_event_handlers(account)
                            self.logger.info(f"为账号 {account.account_id} 启动监控")
                    else:
                        self.logger.warning(f"账号 {account.account_id} 未连接，跳过监控设置")

            self.logger.info("监控引擎启动完成")

        except Exception as e:
            self.logger.error(f"启动监控引擎失败: {e}")

    def add_monitor(self, account_id: str, monitor: BaseMonitor, monitor_key: str = None):
        if account_id not in self.monitors:
            self.monitors[account_id] = []

        if monitor_key:
            self.remove_monitor(account_id, monitor_key)

        self.monitors[account_id].append(monitor)

        self._save_monitors()

        self.logger.info(f"为账号 {account_id} 添加监控器: {monitor.__class__.__name__}")

    def remove_monitor(self, account_id: str, monitor_key: str = None, monitor_type: type = None) -> bool:
        if account_id not in self.monitors:
            return False

        monitors = self.monitors[account_id]
        original_count = len(monitors)

        if monitor_type:
            monitors[:] = [m for m in monitors if not isinstance(m, monitor_type)]
            return len(monitors) < original_count

        if monitor_key:
            try:
                if '_' in monitor_key:
                    parts = monitor_key.split('_')
                    if len(parts) >= 2 and parts[-1].isdigit():
                        index = int(parts[-1])
                        if 0 <= index < len(monitors):
                            monitors.pop(index)
                            self.logger.info(f"移除监控器: {monitor_key}")
                            return True

                monitor_type_name = monitor_key.split('_')[0]
                for i, monitor in enumerate(monitors):
                    if monitor.__class__.__name__ == monitor_type_name:
                        monitors.pop(i)
                        self.logger.info(f"移除监控器: {monitor_key}")
                        return True

            except (ValueError, IndexError) as e:
                self.logger.error(f"解析监控器键值失败: {e}")

        return False

    def get_monitors(self, account_id: str) -> List[BaseMonitor]:
        return self.monitors.get(account_id, [])

    def clear_monitors(self, account_id: str):
        if account_id in self.monitors:
            del self.monitors[account_id]
            self._save_monitors()
            self.logger.info(f"已清除账号 {account_id} 的所有监控器并保存配置")

    def remove_all_monitors(self, account_id: str):
        self.clear_monitors(account_id)

    async def process_message(self, message_event: MessageEvent, account: Account):
        if not self.monitors.get(account.account_id):
            return

        monitors_list = []
        for i, monitor in enumerate(self.monitors[account.account_id]):
            monitor_key = f"{monitor.__class__.__name__}_{i}"
            priority = getattr(monitor.config, 'priority', 50)
            execution_mode = getattr(monitor.config, 'execution_mode', 'merge')
            monitors_list.append((priority, monitor_key, monitor, execution_mode))

        monitors_list.sort(key=lambda x: x[0])

        await self._run_monitors(message_event, account, monitors_list)

    async def _run_monitors(self, message_event: MessageEvent, account: Account,
                                                      monitors_list: list):
        merge_monitors = []
        merge_actions = {
            'email_notify': False,
            'forward_targets': set(),
            'enhanced_forward': False,
            'forward_rewrite': {},
            'log_files': set(),
            'reply_enabled': False,
            'reply_texts': [],
            'reply_delay_min': 0,
            'reply_delay_max': 0,
            'reply_mode': 'reply',
            'reply_content_type': 'custom',
            'ai_reply_prompt': '',
            'custom_actions': []
        }

        for priority, monitor_key, monitor, execution_mode in monitors_list:
            try:
                result = await monitor.process_message(message_event, account)

                if result.result == MonitorResult.MATCHED:
                    self.logger.info(f"✅ 监控器 {monitor_key} 匹配成功 [优先级:{priority}] [模式:{execution_mode}]")

                    if execution_mode == 'first_match':
                        self.logger.info(f"🎯 [首次匹配停止] {monitor_key} 匹配，执行动作后停止")
                        matched_monitors = [{
                            'key': monitor_key,
                            'monitor': monitor,
                            'result': result,
                            'priority': priority
                        }]
                        actions = self._collect_actions(monitor, monitor_key)
                        await self._run_actions(message_event, account, actions, matched_monitors)
                        return

                    elif execution_mode == 'all':
                        self.logger.info(f"🔄 [全部独立执行] {monitor_key} 匹配，独立执行动作")
                        matched_monitors = [{
                            'key': monitor_key,
                            'monitor': monitor,
                            'result': result,
                            'priority': priority
                        }]
                        actions = self._collect_actions(monitor, monitor_key)
                        await self._run_actions(message_event, account, actions, matched_monitors)

                    else:
                        self.logger.info(f"🔗 [合并模式] {monitor_key} 匹配，收集动作待合并")
                        merge_monitors.append({
                            'key': monitor_key,
                            'monitor': monitor,
                            'result': result,
                            'priority': priority
                        })

                        self._merge_monitor_actions(monitor, monitor_key, merge_actions)

            except Exception as e:
                self.logger.error(f"监控器 {monitor_key} 处理消息失败: {e}")

        if merge_monitors:
            self.logger.info(f"🔗 [合并执行] 共 {len(merge_monitors)} 个merge模式监控器，合并执行动作")
            await self._run_actions(message_event, account, merge_actions, merge_monitors)

    def _merge_monitor_actions(self, monitor, monitor_key: str, all_actions: dict):
        config = monitor.config

        if config.email_notify:
            all_actions['email_notify'] = True

        if config.auto_forward and config.forward_targets:
            all_actions['forward_targets'].update(config.forward_targets)
            if config.enhanced_forward:
                all_actions['enhanced_forward'] = True
            all_actions['forward_rewrite'] = config.forward_rewrite_options() or all_actions['forward_rewrite']

        if config.log_file:
            all_actions['log_files'].add(config.log_file)

        if not all_actions['reply_enabled'] and hasattr(config, 'reply_enabled') and config.reply_enabled:
            all_actions['reply_enabled'] = True

            reply_content_type = getattr(config, 'reply_content_type', 'custom')
            if hasattr(reply_content_type, 'value'):
                reply_content_type = reply_content_type.value
            all_actions['reply_content_type'] = reply_content_type

            all_actions['ai_reply_prompt'] = getattr(config, 'ai_reply_prompt', '')

            if hasattr(monitor, 'reply_content'):
                dynamic_reply_texts = monitor.reply_content()
                if dynamic_reply_texts:
                    all_actions['reply_texts'] = dynamic_reply_texts
                    self.logger.debug(f"使用监控器 {monitor_key} 的动态回复内容: {len(dynamic_reply_texts)}条")
                else:
                    config_reply_texts = getattr(config, 'reply_texts', [])
                    if not config_reply_texts and hasattr(config, 'ai_reply_prompt') and getattr(config,
                                                                                                 'ai_reply_prompt'):
                        all_actions['reply_content_type'] = 'ai'
                        all_actions['ai_reply_prompt'] = getattr(config, 'ai_reply_prompt')
                    else:
                        all_actions['reply_texts'] = config_reply_texts
            else:
                all_actions['reply_texts'] = getattr(config, 'reply_texts', [])

            all_actions['reply_delay_min'] = getattr(config, 'reply_delay_min', 0)
            all_actions['reply_delay_max'] = getattr(config, 'reply_delay_max', 0)
            reply_mode_value = getattr(config, 'reply_mode', 'reply')
            if hasattr(reply_mode_value, 'value'):
                reply_mode_value = reply_mode_value.value
            all_actions['reply_mode'] = reply_mode_value

    def _collect_actions(self, monitor, monitor_key: str) -> dict:
        config = monitor.config
        actions = {
            'email_notify': config.email_notify,
            'forward_targets': set(config.forward_targets) if config.auto_forward else set(),
            'enhanced_forward': config.enhanced_forward if config.auto_forward else False,
            'forward_rewrite': config.forward_rewrite_options(),
            'log_files': {config.log_file} if config.log_file else set(),
            'reply_enabled': False,
            'reply_texts': [],
            'reply_delay_min': 0,
            'reply_delay_max': 0,
            'reply_mode': 'reply',
            'reply_content_type': 'custom',
            'ai_reply_prompt': '',
            'custom_actions': []
        }

        if hasattr(config, 'reply_enabled') and config.reply_enabled:
            actions['reply_enabled'] = True

            reply_content_type = getattr(config, 'reply_content_type', 'custom')
            if hasattr(reply_content_type, 'value'):
                reply_content_type = reply_content_type.value
            actions['reply_content_type'] = reply_content_type

            actions['ai_reply_prompt'] = getattr(config, 'ai_reply_prompt', '')

            if hasattr(monitor, 'reply_content'):
                dynamic_reply_texts = monitor.reply_content()
                if dynamic_reply_texts:
                    actions['reply_texts'] = dynamic_reply_texts
                else:
                    actions['reply_texts'] = getattr(config, 'reply_texts', [])
            else:
                actions['reply_texts'] = getattr(config, 'reply_texts', [])

            actions['reply_delay_min'] = getattr(config, 'reply_delay_min', 0)
            actions['reply_delay_max'] = getattr(config, 'reply_delay_max', 0)

            reply_mode_value = getattr(config, 'reply_mode', 'reply')
            if hasattr(reply_mode_value, 'value'):
                reply_mode_value = reply_mode_value.value
            actions['reply_mode'] = reply_mode_value

        return actions

    async def _run_actions(self, message_event: MessageEvent, account: Account,
                                      actions: dict, matched_monitors: list):

        message = message_event.message

        try:
            if actions['email_notify']:
                email_content = await self._build_email(
                    message_event, account, matched_monitors
                )

                asyncio.create_task(self._send_email_async(
                    subject=f"TG监控系统 - 检测到 {len(matched_monitors)} 个匹配",
                    content=email_content,
                    email_addresses=actions.get('email_addresses', []),
                    monitor_count=len(matched_monitors)
                ))

            if actions['forward_targets']:
                target_ids = [tid for tid in actions['forward_targets'] if tid != message.chat_id]

                if target_ids:
                    from .forward import EnhancedForwardService
                    from .forward_store import ForwardStore

                    client = account.client
                    service = EnhancedForwardService()
                    store = ForwardStore()
                    rewrite_options = actions.get('forward_rewrite')

                    for target_id in target_ids:
                        record_id = store.add(
                            account.account_id,
                            message,
                            target_id,
                            actions['enhanced_forward'],
                            rewrite_options
                        )
                        try:
                            if actions['enhanced_forward']:
                                result = await service.forward_message_enhanced(
                                    message=message,
                                    account=account,
                                    target_ids=[target_id],
                                    rewrite_options=rewrite_options
                                )
                                success = bool(result.get(target_id))
                            else:
                                success = await service.copy_message_without_source(
                                    client, message, target_id, rewrite_options
                                )

                            store.mark_result(record_id, success, "" if success else service.last_error or "转发失败")
                            if success:
                                self.logger.info(f"无来源标记复制消息到: {target_id}")
                            else:
                                self.logger.error(f"无来源标记复制消息到 {target_id} 失败")
                        except Exception as e:
                            store.mark_result(record_id, False, str(e))
                            self.logger.error(f"无来源标记复制消息到 {target_id} 失败: {e}")

            for log_file in actions['log_files']:
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{message.timestamp}] {message.text}\n")
                except Exception as e:
                    self.logger.error(f"写入日志文件 {log_file} 失败: {e}")

            if actions['reply_enabled']:
                import random

                delay = random.uniform(
                    actions['reply_delay_min'],
                    actions['reply_delay_max']
                ) if actions['reply_delay_max'] > actions['reply_delay_min'] else actions['reply_delay_min']

                if delay > 0:
                    await asyncio.sleep(delay)

                reply_text = ""
                reply_content_type = actions.get('reply_content_type', 'custom')

                if reply_content_type == 'ai' and actions.get('ai_reply_prompt'):
                    from .ai import AIService
                    ai_service = AIService()

                    if ai_service.is_configured():
                        ai_prompt = f"{actions['ai_reply_prompt']}\n\n原始消息: {message.text or '(非文本消息)'}"

                        ai_response = await ai_service.get_chat_completion([
                            {"role": "user", "content": ai_prompt}
                        ])

                        if ai_response:
                            reply_text = ai_response.strip()
                        else:
                            self.logger.warning("AI服务返回空结果，跳过回复")
                            return
                    else:
                        self.logger.warning("AI服务未配置，跳过AI回复")
                        return
                elif actions['reply_texts']:
                    # NOSONAR - 用于随机选择回复文本以模拟人类行为，不需要密码学安全性
                    reply_text = random.choice(actions['reply_texts'])  # NOSONAR
                else:
                    self.logger.debug("没有可用的回复内容，跳过回复")
                    return

                if not reply_text:
                    self.logger.debug("回复内容为空，跳过回复")
                    return

                client = account.client
                reply_mode = actions.get('reply_mode', 'reply')

                delay_info = f"延迟:{delay:.2f}s" if delay > 0 else "即时"
                reply_preview = reply_text[:30] + "..." if len(reply_text) > 30 else reply_text
                mode_info = "直接发送" if reply_mode == 'send' else "回复消息"

                triggered_monitors = []
                for match in matched_monitors:
                    monitor = match['monitor']
                    monitor_type = monitor.__class__.__name__.replace('Monitor', '')

                    if hasattr(monitor, '_type_info'):
                        type_info = await monitor._type_info()
                    else:
                        type_info = ""

                    triggered_monitors.append(f"{monitor_type}{type_info}")

                monitors_info = " | ".join(triggered_monitors) if len(triggered_monitors) > 1 else triggered_monitors[0]

                try:
                    if reply_mode == 'send':
                        await client.send_message(message.chat_id, reply_text)
                        self.logger.info(
                            f"✅ [{monitors_info}] 频道:{message.chat_id} 发送者:{message.sender.id if message.sender else 'N/A'} [{mode_info}] [{delay_info}] 回复:\"{reply_preview}\"")
                    else:
                        await client.send_message(
                            message.chat_id,
                            reply_text,
                            reply_to=message.message_id
                        )
                        self.logger.info(
                            f"✅ [{monitors_info}] 频道:{message.chat_id} 发送者:{message.sender.id if message.sender else 'N/A'} [{mode_info}] [{delay_info}] 回复:\"{reply_preview}\"")
                except Exception as reply_error:
                    self.logger.error(f"❌ [{monitors_info}] 频道:{message.chat_id} 回复失败: {reply_error}")
                    try:
                        await client.send_message(message.chat_id, reply_text)
                        self.logger.info(
                            f"✅ [{monitors_info}] 频道:{message.chat_id} 发送者:{message.sender.id if message.sender else 'N/A'} [回退-直接发送] [{delay_info}] 回复:\"{reply_preview}\"")
                    except Exception as fallback_error:
                        self.logger.error(f"❌ [{monitors_info}] 频道:{message.chat_id} 回退发送失败: {fallback_error}")

            for match in matched_monitors:
                config = match['monitor'].config
                old_count = config.execution_count
                old_active = config.active

                config.increment_execution()
                new_count = config.execution_count

                self.logger.debug(
                    f"监控器 {match['key']} 执行计数更新: {old_count} → {new_count}/{config.max_executions or '无限制'}")

                if config.is_execution_limit_reached():
                    config.active = False
                    config.reset_execution_count()
                    self.logger.info(f"🛑 监控器 {match['key']} 已执行 {config.max_executions} 次，已暂停并重置执行计数")
                    self._save_monitors()

        except Exception as e:
            self.logger.error(f"执行合并动作时出错: {e}")

    async def _build_email(self, message_event: MessageEvent, account: Account,
                                            matched_monitors: list) -> str:
        """
        构建增强的邮件通知内容

        Args:
            message_event: 消息事件
            account: 账号信息
            matched_monitors: 匹配的监控器列表

        Returns:
            增强的邮件内容
        """
        message = message_event.message

        chat_info = "未知聊天"
        try:
            if hasattr(account, 'client') and account.client:
                entity = await account.client.get_entity(message.chat_id)
                if hasattr(entity, 'title'):
                    chat_info = f"{entity.title} (ID: {message.chat_id})"
                elif hasattr(entity, 'username'):
                    chat_info = f"@{entity.username} (ID: {message.chat_id})"
                else:
                    chat_info = f"聊天ID: {message.chat_id}"
        except Exception:
            chat_info = f"聊天ID: {message.chat_id}"

        sender_info = "未知发送者"
        if message.sender:
            sender_name = message.sender.full_name or "未知用户"
            sender_username = f"@{message.sender.username}" if message.sender.username else ""
            sender_info = f"{sender_name} {sender_username} (ID: {message.sender.id})".strip()

        email_content = "=" * 50 + "\n"
        email_content += "📢 TG监控系统 - 消息匹配通知\n"
        email_content += "=" * 50 + "\n\n"

        email_content += "📍 基本信息：\n"
        email_content += f"⏰ 时间：{message.timestamp}\n"
        email_content += f"👤 发送者：{sender_info}\n"
        email_content += f"💬 聊天：{chat_info}\n"
        email_content += f"🎯 监控账号：{account.account_id}\n\n"

        email_content += "📝 消息内容：\n"
        if message.text:
            message_text = message.text[:500] + "..." if len(message.text) > 500 else message.text
            email_content += f'"{message_text}"\n\n'
        else:
            email_content += "[无文字内容]\n\n"

        email_content += "📄 消息类型：\n"
        if message.media and message.media.has_media:
            email_content += f"📎 媒体类型：{message.media.media_type}\n"
            if message.media.file_name:
                email_content += f"📁 文件名：{message.media.file_name}\n"
            if message.media.file_size:
                email_content += f"📐 文件大小：{message.media.file_size / 1024 / 1024:.2f} MB\n"
        else:
            email_content += "📄 普通文字消息\n"

        if message.has_buttons:
            email_content += f"🔘 包含按钮：{', '.join(message.button_texts)}\n"

        if message.is_forwarded:
            email_content += "🔄 转发消息\n"

        email_content += "\n"

        email_content += "🎯 匹配的监控器：\n"
        for i, match in enumerate(matched_monitors, 1):
            monitor = match['monitor']
            monitor_type = monitor.__class__.__name__.replace('Monitor', '')

            email_content += f"{i}. 【{monitor_type}监控器】\n"

            if hasattr(monitor, 'config'):
                config = monitor.config

                if monitor_type == 'Keyword':
                    keyword = getattr(config, 'keyword', '未知')
                    match_type = getattr(config, 'match_type', '未知')
                    email_content += f"   🔍 关键词：{keyword}\n"
                    email_content += f"   📋 匹配类型：{match_type}\n"

                elif monitor_type == 'AI':
                    ai_prompt = getattr(config, 'ai_prompt', '未知')[:100]
                    email_content += f"   🤖 AI提示词：{ai_prompt}...\n"

                elif monitor_type == 'File':
                    file_ext = getattr(config, 'file_extension', '未知')
                    email_content += f"   📄 文件类型：{file_ext}\n"

                elif monitor_type == 'AllMessages':
                    email_content += f"   📊 全量监控\n"

                execution_count = getattr(config, 'execution_count', 0)
                max_executions = getattr(config, 'max_executions', None)
                if max_executions:
                    email_content += f"   📈 执行次数：{execution_count}/{max_executions}\n"
                else:
                    email_content += f"   📈 执行次数：{execution_count}\n"

            email_content += "\n"

        email_content += "-" * 30 + "\n"
        email_content += "🔧 系统信息：\n"
        email_content += f"📧 此邮件由 TG监控系统 自动发送\n"
        email_content += f"⚙️ 监控引擎版本：v2.0\n"

        return email_content

    async def process_event(self, event: events.NewMessage, account: Account):
        try:
            if not account.monitor_active:
                return

            sender = await event.get_sender()
            if not sender:
                sender = self._create_pseudo_sender(event)

            message_sender = MessageSender.from_telethon_entity(sender)

            telegram_message = TelegramMessage.from_telethon_event(event, message_sender)

            if event.message.media:
                self.logger.debug(f"消息包含媒体: {type(event.message.media).__name__}")
                if hasattr(event.message.media, 'document') and event.message.media.document:
                    self.logger.debug(f"消息包含文档")
                    if hasattr(event.message.media.document, 'attributes'):
                        for attr in event.message.media.document.attributes:
                            if hasattr(attr, 'file_name'):
                                self.logger.debug(f"文件名: {attr.file_name}")
                                break

            message_event = MessageEvent(
                account_id=account.account_id,
                message=telegram_message
            )

            if telegram_message.grouped_id:
                await asyncio.sleep(self.ALBUM_GATHER_DELAY_SECONDS)

            if self._is_message_processed(message_event):
                return

            self._mark_message_processed(message_event)

            await self.process_message(message_event, account)

        except Exception as e:
            self.logger.error(f"处理消息事件时出错: {e}")

    def _create_pseudo_sender(self, event):

        class PseudoSender:
            def __init__(self, event):
                self.id = event.chat_id or 0
                self.username = ""
                post_author = getattr(event.message, 'post_author', None)
                self.first_name = post_author or "未知"
                self.last_name = ""
                self.bot = False
                self.title = post_author

        return PseudoSender(event)

    def _is_message_processed(self, message_event: MessageEvent) -> bool:
        return message_event.unique_id in self.processed_messages_set

    def _mark_message_processed(self, message_event: MessageEvent):
        msg_id = message_event.unique_id
        if len(self.processed_messages) >= self.processed_messages.maxlen:
            # Remove oldest from the lookup set when deque evicts
            oldest = self.processed_messages[0]
            self.processed_messages_set.discard(oldest)
        self.processed_messages.append(msg_id)
        self.processed_messages_set.add(msg_id)

    def _log_processing_results(self, message_event: MessageEvent, results: List):
        matched_count = 0
        error_count = 0

        for result in results:
            if isinstance(result, Exception):
                error_count += 1
            elif hasattr(result, 'result') and result.result == MonitorResult.MATCHED:
                matched_count += 1

        if matched_count > 0 or error_count > 0:
            self.logger.info(
                f"消息处理完成: 聊天={message_event.message.chat_id}, "
                f"匹配={matched_count}, 错误={error_count}"
            )

    def setup_event_handlers(self, account: Account):
        if not account.client:
            return

        account.client.add_event_handler(
            lambda event: self.process_event(event, account),
            events.NewMessage()
        )

        self.logger.info(f"为账号 {account.account_id} 设置事件处理器")

    def get_statistics(self) -> Dict[str, int]:
        return {
            "total_accounts": len(self.monitors),
            "total_monitors": sum(len(monitors) for monitors in self.monitors.values()),
            "processed_messages": len(self.processed_messages_set)
        }

    def add_scheduled_message(self, config):
        try:
            message_dict = {
                'job_id': config.job_id,
                'target_id': config.target_id,
                'channel_id': config.target_id,
                'message': config.message,
                'cron': config.cron,
                'schedule': config.cron,
                'account_id': config.account_id,
                'random_offset': getattr(config, 'random_offset', 0),
                'random_delay': getattr(config, 'random_offset', 0),
                'delete_after_sending': getattr(config, 'delete_after_sending', False),
                'delete_after_send': getattr(config, 'delete_after_sending', False),
                'max_executions': getattr(config, 'max_executions', None),
                'execution_count': 0,
                'created_at': str(config.created_at) if hasattr(config, 'created_at') else None,
                'enabled': True,
                'active': True,
                'use_ai': getattr(config, 'use_ai', False),
                'ai_prompt': getattr(config, 'ai_prompt', None),
                'ai_model': getattr(config, 'ai_model', 'gpt-4o'),
                'schedule_mode': getattr(config, 'schedule_mode', 'cron')
            }

            self.scheduled_messages.append(message_dict)

            self._save_scheduled_messages()

            self.logger.info(f"添加定时消息: {config.job_id}")

            self._start_scheduler()

            if self.scheduler and self.scheduler.running:
                try:
                    schedule_mode = getattr(config, 'schedule_mode', 'cron')
                    if schedule_mode == 'interval':
                        parts = config.cron.split()
                        hours = int(parts[0]) if len(parts) > 0 else 0
                        minutes = int(parts[1]) if len(parts) > 1 else 0

                        trigger = IntervalTrigger(
                            hours=hours,
                            minutes=minutes,
                            timezone=pytz.timezone('Asia/Shanghai')
                        )
                        self.logger.info(f"使用间隔触发器: {hours}小时 {minutes}分钟")
                    else:
                        trigger = CronTrigger.from_crontab(config.cron, timezone=pytz.timezone('Asia/Shanghai'))
                        self.logger.info(f"使用Cron触发器: {config.cron}")

                    self.scheduler.add_job(
                        self._run_scheduled,
                        trigger,
                        id=config.job_id,
                        args=[config.job_id],
                        replace_existing=True
                    )
                    self.logger.info(f"已启动定时任务: {config.job_id}")
                except Exception as scheduler_error:
                    self.logger.error(f"添加调度任务失败: {scheduler_error}")
            else:
                self.logger.warning(f"调度器未启动，定时消息任务将延后添加: {config.job_id}")

        except Exception as e:
            self.logger.error(f"添加定时消息失败: {e}")

    def get_scheduled_messages(self):
        return self.scheduled_messages

    async def _run_scheduled(self, job_id: str):
        try:
            message_config = None
            for msg in self.scheduled_messages:
                if msg['job_id'] == job_id:
                    message_config = msg
                    break

            if not message_config:
                self.logger.error(f"未找到定时消息配置: {job_id}")
                return

            if not message_config.get('active', True):
                self.logger.debug(f"定时消息已暂停，跳过执行: {job_id}")
                return

            max_executions = message_config.get('max_executions')
            execution_count = message_config.get('execution_count', 0)

            if max_executions and execution_count >= max_executions:
                self.logger.info(f"定时消息达到执行次数限制，停止执行: {job_id}")
                try:
                    self.scheduler.remove_job(job_id)
                except Exception:
                    pass
                return

            account_id = message_config.get('account_id')
            target_id = message_config.get('target_id')
            message_text = message_config.get('message', '')

            if not account_id or not target_id:
                self.logger.error(f"定时消息配置不完整: account_id={account_id}, target_id={target_id}")
                return

            from .account import AccountManager
            account_manager = AccountManager()
            account = account_manager.get_account(account_id)

            if not account or not account.client:
                self.logger.error(f"账号未找到或未连接: {account_id}")
                return

            if message_config.get('use_ai', False) and message_config.get('ai_prompt'):
                try:
                    from .ai import AIService
                    ai_service = AIService()

                    if ai_service.is_configured():
                        self.logger.info(f"🤖 开始AI内容生成: {job_id}")

                        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        enhanced_prompt = f"""
当前时间: {current_time}
任务ID: {job_id}
目标聊天: {target_id}

用户提示词: {message_config.get('ai_prompt')}

请根据上述信息生成合适的消息内容。要求：
1. 内容要符合用户的提示词要求
2. 可以包含当前时间信息（如果相关）
3. 内容要简洁明了，适合发送到Telegram
4. 直接返回消息内容，不要包含额外的解释

请生成消息内容：
"""

                        ai_response = await ai_service.get_chat_completion([
                            {"role": "user", "content": enhanced_prompt}
                        ])

                        if ai_response and ai_response.strip():
                            message_text = ai_response.strip()
                            self.logger.info(
                                f"✅ AI内容生成成功: \"{message_text[:50]}{'...' if len(message_text) > 50 else ''}\"")
                        else:
                            self.logger.warning(f"⚠️ AI返回空内容，跳过此次执行")
                            return
                    else:
                        self.logger.error(f"❌ AI服务未配置，跳过此次执行")
                        return

                except Exception as ai_error:
                    self.logger.error(f"❌ AI生成内容失败: {ai_error}")
                    return

            if not message_text or not message_text.strip():
                self.logger.error(f"❌ 消息内容为空，跳过发送: {job_id}")
                return

            random_delay = message_config.get('random_delay', message_config.get('random_offset', 0))
            if random_delay > 0:
                import random  # NOSONAR - 用于模拟人类发送延迟，不需要密码学安全性
                actual_delay = random.randint(0, random_delay)  # NOSONAR
                self.logger.info(f"⏰ 定时消息延时发送: {actual_delay} 秒 (最大延时: {random_delay} 秒)")
                await asyncio.sleep(actual_delay)

            try:
                if isinstance(target_id, str):
                    target_id = int(target_id)

                try:
                    entity = await account.client.get_entity(target_id)
                    self.logger.debug(
                        f"✅ 目标实体验证成功: {target_id} -> {getattr(entity, 'title', getattr(entity, 'username', target_id))}")
                except Exception as entity_error:
                    self.logger.error(f"❌ 无法找到目标实体 {target_id}: {entity_error}")
                    self.logger.error(f"💡 解决方案：请检查目标ID是否正确，或账号是否有权限访问此频道/群组")
                    return

                await account.client.send_message(target_id, message_text)

            except ValueError as ve:
                self.logger.error(f"❌ 无效的目标ID格式: {target_id}, 错误: {ve}")
                return
            except Exception as send_error:
                self.logger.error(f"❌ 发送消息失败到目标 {target_id}: {send_error}")
                return

            old_count = execution_count
            message_config['execution_count'] = execution_count + 1
            new_count = message_config['execution_count']
            max_executions = message_config.get('max_executions')

            self.logger.info(f"✅ 定时消息执行成功: {job_id} -> {target_id}")
            self.logger.info(f"📊 执行统计更新: {old_count} → {new_count}/{max_executions or '无限制'} 次")
            if random_delay > 0:
                self.logger.info(f"⏰ 延时设置: {random_delay} 秒")

            self._save_scheduled_messages()

            if max_executions and message_config['execution_count'] >= max_executions:
                try:
                    if self.scheduler and self.scheduler.running:
                        try:
                            self.scheduler.pause_job(job_id)
                            self.logger.info(f"⏸️ 定时消息任务已暂停: {job_id}")
                        except Exception as pause_error:
                            self.scheduler.remove_job(job_id)
                            self.logger.warning(f"无法暂停任务，已移除: {job_id}")

                    message_config['active'] = False

                    self._save_scheduled_messages()
                    self.logger.info(f"🛑 定时消息已达到执行限制 ({max_executions} 次)，已暂停任务: {job_id}")
                except Exception as pause_error:
                    self.logger.error(f"暂停达到限制的定时任务失败: {pause_error}")
            else:
                self.logger.info(
                    f"📈 定时消息继续运行，剩余执行次数: {max_executions - message_config['execution_count'] if max_executions else '无限制'}")

            if message_config.get('delete_after_send', False):
                try:
                    pass
                except Exception as delete_error:
                    self.logger.error(f"删除消息失败: {delete_error}")

        except Exception as e:
            self.logger.error(f"执行定时消息失败 {job_id}: {e}")

    def remove_scheduled_message(self, job_id: str):
        try:
            original_count = len(self.scheduled_messages)
            self.scheduled_messages = [msg for msg in self.scheduled_messages if msg.get('job_id') != job_id]

            if len(self.scheduled_messages) < original_count:
                if self.scheduler and self.scheduler.running:
                    try:
                        self.scheduler.remove_job(job_id)
                        self.logger.info(f"从调度器中移除任务: {job_id}")
                    except Exception as scheduler_error:
                        self.logger.warning(f"从调度器移除任务失败 {job_id}: {scheduler_error}")
                else:
                    self.logger.debug(f"调度器未运行，跳过移除任务: {job_id}")

                self._save_scheduled_messages()
                self.logger.info(f"删除定时消息: {job_id}")

                return True
            else:
                self.logger.warning(f"未找到定时消息: {job_id}")
                return False

        except Exception as e:
            self.logger.error(f"删除定时消息失败: {e}")
            return False

    def _save_scheduled_messages(self):
        try:
            messages_copy = copy.deepcopy(self.scheduled_messages)
            atomic_write_json(self.scheduled_messages_file, messages_copy, self._save_lock)

            self.logger.info(f"已保存 {len(messages_copy)} 条定时消息")

        except Exception as e:
            self.logger.error(f"保存定时消息任务失败: {e}")

    def _load_scheduled(self):
        if not self.scheduled_messages_file.exists():
            self.logger.info("定时消息文件不存在，跳过加载")
            return

        try:
            data = read_json_file(self.scheduled_messages_file, [])

            self.scheduled_messages = data
            self.logger.info(f"已加载 {len(self.scheduled_messages)} 条定时消息")

        except Exception as e:
            self.logger.error(f"加载定时消息文件失败: {e}")

    async def _send_email(self, subject: str, content: str, email_addresses: list = None):
        if not email_addresses:
            try:
                from .config import config
                default_emails = []
                if hasattr(config, 'EMAIL_TO') and config.EMAIL_TO:
                    default_emails = [config.EMAIL_TO]
                elif hasattr(config, 'email_to') and config.email_to:
                    default_emails = [config.email_to]

                if not default_emails:
                    self.logger.warning("未配置邮件接收地址，跳过邮件通知")
                    return

                email_addresses = default_emails
            except Exception as e:
                self.logger.error(f"读取邮件配置失败: {e}")
                return

        def _do_send():
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                from email.header import Header
                from .config import config

                smtp_host = getattr(config, 'EMAIL_SMTP_SERVER', None) or getattr(config, 'SMTP_HOST',
                                                                                  None) or 'smtp.qq.com'
                smtp_port = getattr(config, 'EMAIL_SMTP_PORT', None) or getattr(config, 'SMTP_PORT', None) or 465
                email_from = getattr(config, 'EMAIL_FROM', None) or getattr(config, 'EMAIL_USERNAME', None)
                email_password = getattr(config, 'EMAIL_PASSWORD', None)

                try:
                    smtp_port = int(smtp_port)
                except (ValueError, TypeError):
                    smtp_port = 465

                self.logger.debug(
                    f"邮件配置读取: SMTP={smtp_host}:{smtp_port}, FROM={email_from}, PASSWORD={'已配置' if email_password else '未配置'}")

                if not email_from or not email_password:
                    missing_fields = []
                    if not email_from: missing_fields.append('EMAIL_FROM 或 EMAIL_USERNAME')
                    if not email_password: missing_fields.append('EMAIL_PASSWORD')

                    self.logger.warning(f"邮件服务器配置不完整，缺少字段: {', '.join(missing_fields)}")
                    self.logger.warning("请在.env文件中配置：EMAIL_FROM=your@email.com 和 EMAIL_PASSWORD=your_password")
                    return

                msg = MIMEMultipart()
                msg['From'] = email_from
                msg['To'] = ', '.join(email_addresses)
                msg['Subject'] = Header(subject, 'utf-8')

                msg.attach(MIMEText(content, 'plain', 'utf-8'))

                server = smtplib.SMTP_SSL(smtp_host, int(smtp_port))
                server.login(email_from, email_password)

                for email in email_addresses:
                    server.sendmail(email_from, [email], msg.as_string())

                server.quit()

                self.logger.debug(f"邮件通知发送成功，接收者: {', '.join(email_addresses)}")
                self.logger.debug(f"使用配置: {smtp_host}:{smtp_port}, 发件人: {email_from}")

            except Exception as e:
                self.logger.error(f"发送邮件通知失败: {e}")
                self.logger.error(f"邮件配置：SMTP_HOST={smtp_host}, "
                                  f"SMTP_PORT={smtp_port}, EMAIL_FROM={email_from}")
                                  
        await asyncio.to_thread(_do_send)

    def get_system_stats(self) -> dict:
        total_monitors = sum(len(monitors) for monitors in self.monitors.values())
        return {
            "total_monitors": total_monitors,
            "scheduled_messages": len(self.scheduled_messages),
            "processed_messages": len(self.processed_messages)
        }

    async def _send_email_async(
            self,
            subject: str,
            content: str,
            email_addresses: list = None,
            monitor_count: int = 1
    ):
        try:
            await self._send_email(subject, content, email_addresses)
            self.logger.debug(f"邮件通知已后台发送完成 ({monitor_count}个监控器)")
        except Exception as e:
            self.logger.error(f"后台邮件发送失败: {e}")
