import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

from core.account import AccountManager
from core.forward import EnhancedForwardService
from core.model import (
    Account,
    AccountConfig,
    BaseMonitorConfig,
    KeywordConfig,
    MatchType,
    MessageMedia,
    MessageEvent,
    MessageSender,
    MonitorConfig,
    TelegramMessage,
)
from core.storage import atomic_write_json, read_json_file
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


def make_album_message(grouped_id=12345):
    return TelegramMessage(
        message_id=10,
        chat_id=20,
        sender=MessageSender(1),
        text="caption",
        timestamp=datetime.now(),
        media=MessageMedia(has_media=True, media_type="photo"),
        grouped_id=grouped_id,
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


def test_forward_rewrite_options_respect_forward_state():
    disabled = BaseMonitorConfig(forward_rewrite_enabled=True)
    enabled = BaseMonitorConfig(
        auto_forward=True,
        forward_rewrite_enabled=True,
        forward_rewrite_template="更多{topic}",
        forward_rewrite_prompt="清理广告"
    )

    assert disabled.forward_rewrite_options() == {}
    assert enabled.forward_rewrite_options() == {
        "enabled": True,
        "template": "更多{topic}",
        "prompt": "清理广告"
    }


class FakeClient:
    def __init__(self, original_message, nearby_messages=None):
        self.original_message = original_message
        self.nearby_messages = nearby_messages or []
        self.sent = []
        self.sent_files = []

    async def get_messages(self, chat_id, *args, **kwargs):
        if "ids" in kwargs:
            return self.original_message
        return self.nearby_messages

    async def send_message(self, target_id, message):
        self.sent.append((target_id, message))

    async def send_file(self, target_id, files, caption=None):
        self.sent_files.append((target_id, files, caption))


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


def test_copy_message_without_source_preserves_album_as_single_send_file_call():
    service = EnhancedForwardService()
    first = SimpleNamespace(id=10, grouped_id=555, media="photo-1", message="caption")
    second = SimpleNamespace(id=11, grouped_id=555, media="photo-2", message="")
    unrelated = SimpleNamespace(id=12, grouped_id=999, media="photo-3", message="")
    client = FakeClient(first, nearby_messages=[second, unrelated, first])

    ok = asyncio.run(service.copy_message_without_source(client, make_album_message(grouped_id=555), 99))

    assert ok is True
    assert client.sent == []
    assert client.sent_files == [(99, ["photo-1", "photo-2"], ["caption", ""])]


def test_grouped_message_unique_id_deduplicates_album_parts():
    first = MessageEvent(account_id="acc", message=make_album_message(grouped_id=555))
    second = MessageEvent(account_id="acc", message=make_album_message(grouped_id=555))
    second.message.message_id = 11

    assert first.unique_id == second.unique_id


def test_copy_message_without_source_rewrites_text_when_enabled(monkeypatch):
    class FakeAIService:
        async def rewrite_forward_text(self, text, append_template="", custom_prompt=""):
            return {"topic": "财经", "final_text": "清理后的新闻\n\n我的广告"}

    import core.ai

    monkeypatch.setattr(core.ai, "AIService", FakeAIService)
    service = EnhancedForwardService()
    client = FakeClient(SimpleNamespace(media=None))
    rewrite_options = {"enabled": True, "template": "{topic}", "prompt": ""}

    ok = asyncio.run(service.copy_message_without_source(client, make_message(MessageSender(1)), 99, rewrite_options))

    assert ok is True
    assert client.sent == [(99, "清理后的新闻\n\n我的广告")]


def test_album_rewrite_updates_first_caption_only(monkeypatch):
    class FakeAIService:
        async def rewrite_forward_text(self, text, append_template="", custom_prompt=""):
            return {"topic": "科技", "final_text": "清理后的图集说明"}

    import core.ai

    monkeypatch.setattr(core.ai, "AIService", FakeAIService)
    service = EnhancedForwardService()
    first = SimpleNamespace(id=10, grouped_id=555, media="photo-1", message="原始广告图集说明")
    second = SimpleNamespace(id=11, grouped_id=555, media="photo-2", message="")
    client = FakeClient(first, nearby_messages=[first, second])
    rewrite_options = {"enabled": True, "template": "", "prompt": ""}

    ok = asyncio.run(service.copy_message_without_source(client, make_album_message(grouped_id=555), 99, rewrite_options))

    assert ok is True
    assert client.sent_files == [(99, ["photo-1", "photo-2"], ["清理后的图集说明", ""])]


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


def test_atomic_write_json_replaces_file_without_temp_leftover(tmp_path):
    target = tmp_path / "state.json"

    atomic_write_json(target, {"version": 1})
    atomic_write_json(target, {"version": 2})

    assert read_json_file(target, {}) == {"version": 2}
    assert not target.with_suffix(".json.tmp").exists()
