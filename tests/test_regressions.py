import asyncio
import json
from datetime import datetime

from core.account import AccountManager
from core.forward import EnhancedForwardService
from core.model import (
    Account,
    AccountConfig,
    BaseMonitorConfig,
    KeywordConfig,
    MatchType,
    MessageEvent,
    MessageSender,
    MonitorConfig,
    TelegramMessage,
)
from monitor.base import BaseMonitor, MonitorResult


class DummyMonitor(BaseMonitor):
    async def _match(self, message_event, account):
        return True


def make_message(sender=None):
    return TelegramMessage(
        message_id=10,
        chat_id=20,
        sender=sender,
        text="hello",
        timestamp=datetime.now(),
    )


def test_base_monitor_missing_sender_returns_no_match():
    monitor = DummyMonitor(BaseMonitorConfig())
    account = Account("acc", AccountConfig("+12025551234", 123, "a" * 32), own_user_id=1)
    event = MessageEvent(account_id="acc", message=make_message(sender=None))

    result = asyncio.run(monitor.process_message(event, account))

    assert result.result is MonitorResult.NO_MATCH
    assert result.error is None


def test_blocked_users_accepts_string_or_int_ids():
    sender = MessageSender(id=123)
    event = MessageEvent(account_id="acc", message=make_message(sender=sender))
    monitor = DummyMonitor(BaseMonitorConfig(blocked_users=["123"], blocked_bots=["456"]))

    assert monitor._is_blocked(event) is True


def test_monitor_config_round_trip_preserves_enum_values():
    config = MonitorConfig(
        keyword_configs={
            "hello": KeywordConfig(keyword="hello", match_type=MatchType.EXACT)
        }
    )

    payload = config.to_dict()
    restored = MonitorConfig.from_dict(json.loads(json.dumps(payload)))

    assert payload["keyword_configs"]["hello"]["match_type"] == "exact"
    assert restored.keyword_configs["hello"].match_type is MatchType.EXACT


class FakeClient:
    def __init__(self, original_message):
        self.original_message = original_message
        self.sent = []

    async def get_messages(self, chat_id, ids):
        return self.original_message

    async def send_message(self, target_id, message):
        self.sent.append((target_id, message))


def test_copy_message_without_source_success():
    service = EnhancedForwardService()
    original = object()
    client = FakeClient(original)

    ok = asyncio.run(service.copy_message_without_source(client, make_message(MessageSender(1)), 99))

    assert ok is True
    assert client.sent == [(99, original)]


def test_copy_message_without_source_missing_original_returns_false():
    service = EnhancedForwardService()
    client = FakeClient(None)

    ok = asyncio.run(service.copy_message_without_source(client, make_message(MessageSender(1)), 99))

    assert ok is False
    assert client.sent == []


def test_account_save_writes_valid_json_atomically(tmp_path):
    AccountManager.clear_instance()
    manager = AccountManager()
    manager.accounts_file = tmp_path / "account.json"
    manager.accounts.clear()

    account = Account("acc", AccountConfig("+12025551234", 123, "a" * 32))
    manager.add_account(account)

    data = json.loads(manager.accounts_file.read_text(encoding="utf-8"))
    assert data["accounts"][0]["account_id"] == "acc"
    assert not manager.accounts_file.with_suffix(".json.tmp").exists()

    AccountManager.clear_instance()
