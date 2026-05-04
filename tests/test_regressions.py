import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from core.account import AccountManager
from core.ai import AIService
from core.config import Config, config as app_config
from core.engine import MonitorEngine
from core.forward import EnhancedForwardService
from core.forward_store import ForwardStore
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
from web.app import WebApp
from web.wizard import ConfigWizard


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
    string_false = BaseMonitorConfig(auto_forward="false", forward_rewrite_enabled="true")
    enabled = BaseMonitorConfig(
        auto_forward=True,
        forward_rewrite_enabled=True,
        forward_rewrite_template="更多{topic}",
        forward_rewrite_prompt="清理广告"
    )

    assert disabled.forward_rewrite_options() == {}
    assert string_false.forward_rewrite_options() == {}
    assert enabled.forward_rewrite_options() == {
        "enabled": True,
        "template": "更多{topic}",
        "prompt": "清理广告"
    }


def test_wizard_keyword_rewrite_flag_is_saved_as_boolean():
    ConfigWizard.clear_instance()
    wizard = ConfigWizard()

    config = wizard._make_keyword({
        "keyword": "新闻",
        "match_type": "partial",
        "chats": "-1001",
        "auto_forward": "on",
        "forward_targets": "-1002",
        "forward_rewrite_enabled": "on",
        "forward_rewrite_template": "{clean_text}\n\n关注{topic}",
        "forward_rewrite_prompt": "删除广告"
    })

    assert config.auto_forward is True
    assert config.forward_rewrite_enabled is True
    assert config.forward_rewrite_options()["template"] == "{clean_text}\n\n关注{topic}"

    ConfigWizard.clear_instance()


def test_rewrite_forward_text_keeps_json_contract_for_custom_rule(monkeypatch):
    AIService.clear_instance()
    service = AIService()
    prompts = []

    async def fake_completion(messages, *args, **kwargs):
        prompts.append(messages[0]["content"])
        return '{"topic":"财经","clean_text":"AI总结正文"}'

    monkeypatch.setattr(service, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(service, "is_configured", lambda: True)
    monkeypatch.setattr(service, "get_chat_completion", fake_completion)

    result = asyncio.run(service.rewrite_forward_text(
        "原文广告",
        "{clean_text}\n\n更多{topic}",
        "删除联系方式"
    ))

    assert "请只返回 JSON" in prompts[0]
    assert "删除联系方式" in prompts[0]
    assert "不要总结、改写、清理、压缩或重排原文正文" in prompts[0]
    assert result["final_text"] == "原文广告\n\n更多财经"
    assert result["clean_text"] == "原文广告"

    AIService.clear_instance()


def test_rewrite_forward_text_appends_plain_template(monkeypatch):
    AIService.clear_instance()
    service = AIService()

    async def fake_completion(messages, *args, **kwargs):
        return '{"topic":"科技","clean_text":"AI总结正文"}'

    monkeypatch.setattr(service, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(service, "is_configured", lambda: True)
    monkeypatch.setattr(service, "get_chat_completion", fake_completion)

    result = asyncio.run(service.rewrite_forward_text("原文广告", "关注{topic}", ""))

    assert result["final_text"] == "原文广告\n\n关注科技"

    AIService.clear_instance()


def test_rewrite_forward_text_supports_original_text_variable(monkeypatch):
    AIService.clear_instance()
    service = AIService()

    async def fake_completion(messages, *args, **kwargs):
        return '{"topic":"民生"}'

    monkeypatch.setattr(service, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(service, "is_configured", lambda: True)
    monkeypatch.setattr(service, "get_chat_completion", fake_completion)

    result = asyncio.run(service.rewrite_forward_text(
        "原新闻正文\n第二行",
        "{original_text}\n\n本频道持续关注{topic}",
        ""
    ))

    assert result["final_text"] == "原新闻正文\n第二行\n\n本频道持续关注民生"
    assert result["original_text"] == "原新闻正文\n第二行"

    AIService.clear_instance()


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


def test_copy_message_without_source_deduplicates_album_messages():
    service = EnhancedForwardService()
    first = SimpleNamespace(id=10, grouped_id=555, media="photo-1", message="caption")
    second = SimpleNamespace(id=11, grouped_id=555, media="photo-2", message="")
    client = FakeClient(first, nearby_messages=[first, second, first])

    ok = asyncio.run(service.copy_message_without_source(client, make_album_message(grouped_id=555), 99))

    assert ok is True
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


def test_copy_message_without_source_blocks_original_when_rewrite_fails(monkeypatch):
    class FakeAIService:
        async def rewrite_forward_text(self, text, append_template="", custom_prompt=""):
            raise RuntimeError("quota exceeded")

    import core.ai

    monkeypatch.setattr(core.ai, "AIService", FakeAIService)
    service = EnhancedForwardService()
    client = FakeClient(SimpleNamespace(media=None))
    rewrite_options = {"enabled": True, "template": "{topic}", "prompt": ""}

    ok = asyncio.run(service.copy_message_without_source(client, make_message(MessageSender(1)), 99, rewrite_options))

    assert ok is False
    assert client.sent == []
    assert client.sent_files == []
    assert "已阻止原文转发" in service.last_error


def test_string_false_rewrite_option_does_not_trigger_ai(monkeypatch):
    class FakeAIService:
        async def rewrite_forward_text(self, text, append_template="", custom_prompt=""):
            raise AssertionError("AI should not be called")

    import core.ai

    monkeypatch.setattr(core.ai, "AIService", FakeAIService)
    service = EnhancedForwardService()
    original = SimpleNamespace(media=None)
    client = FakeClient(original)

    ok = asyncio.run(service.copy_message_without_source(
        client,
        make_message(MessageSender(1)),
        99,
        {"enabled": "false", "template": "{topic}", "prompt": ""}
    ))

    assert ok is True
    assert client.sent == [(99, original)]


def test_enhanced_forward_does_not_fallback_to_original_when_rewrite_fails(monkeypatch):
    class FakeAIService:
        async def rewrite_forward_text(self, text, append_template="", custom_prompt=""):
            raise RuntimeError("api down")

    import core.ai

    monkeypatch.setattr(core.ai, "AIService", FakeAIService)
    service = EnhancedForwardService()
    client = FakeClient(SimpleNamespace(media=None))
    account = SimpleNamespace(client=client)
    rewrite_options = {"enabled": True, "template": "{topic}", "prompt": ""}

    result = asyncio.run(service.forward_message_enhanced(
        make_message(MessageSender(1)), account, [99], rewrite_options=rewrite_options
    ))

    assert result == {99: False}
    assert client.sent == []
    assert client.sent_files == []
    assert "已阻止原文转发" in service.last_error


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


def test_album_rewrite_blocks_original_caption_when_rewrite_fails(monkeypatch):
    class FakeAIService:
        async def rewrite_forward_text(self, text, append_template="", custom_prompt=""):
            return {}

    import core.ai

    monkeypatch.setattr(core.ai, "AIService", FakeAIService)
    service = EnhancedForwardService()
    first = SimpleNamespace(id=10, grouped_id=555, media="photo-1", message="原始广告图集说明")
    second = SimpleNamespace(id=11, grouped_id=555, media="photo-2", message="")
    client = FakeClient(first, nearby_messages=[first, second])
    rewrite_options = {"enabled": True, "template": "", "prompt": ""}

    ok = asyncio.run(service.copy_message_without_source(client, make_album_message(grouped_id=555), 99, rewrite_options))

    assert ok is False
    assert client.sent_files == []


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


def test_config_ignores_blank_optional_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TG_API_ID", "12345")
    monkeypatch.setenv("TG_API_HASH", "a" * 32)
    monkeypatch.setenv("OPENAI_MODEL", " ")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "")
    monkeypatch.setenv("WEB_PORT", "")
    monkeypatch.setenv("WEB_USERNAME", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DOWNLOADS_DIR", str(tmp_path / "dl"))

    cfg = Config()

    assert cfg.OPENAI_MODEL == "gpt-3.5-turbo"
    assert cfg.OPENAI_BASE_URL == "https://api.openai.com/v1"
    assert cfg.EMAIL_SMTP_PORT == 587
    assert cfg.WEB_PORT == 8000
    assert cfg.WEB_USERNAME == "admin"


def test_config_keeps_default_for_invalid_int_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TG_API_ID", "12345")
    monkeypatch.setenv("TG_API_HASH", "a" * 32)
    monkeypatch.setenv("WEB_PORT", "invalid")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DOWNLOADS_DIR", str(tmp_path / "dl"))

    assert Config().WEB_PORT == 8000


def test_account_config_defaults_session_under_data_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config, "DATA_DIR", str(tmp_path / "data"))

    cfg = AccountConfig("+12025551234", 123, "a" * 32)

    assert Path(cfg.session_name) == tmp_path / "data" / "sessions" / "session_12025551234"
    assert Path(cfg.session_name).parent.exists()


def test_account_manager_migrates_legacy_session_to_data_sessions(monkeypatch, tmp_path):
    AccountManager.clear_instance()
    data_dir = tmp_path / "data"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_config, "DATA_DIR", str(data_dir))

    data_dir.mkdir()
    (tmp_path / "session_12025551234.session").write_text("legacy", encoding="utf-8")
    atomic_write_json(data_dir / "account.json", {
        "accounts": [{
            "account_id": "+12025551234",
            "config": {
                "phone": "+12025551234",
                "api_id": 123,
                "api_hash": "a" * 32,
                "proxy": None,
                "session_name": "session_12025551234"
            },
            "own_user_id": 1,
            "monitor_active": True,
            "monitor_configs": {}
        }]
    })

    manager = AccountManager()
    session_name = manager.get_account("+12025551234").config.session_name

    assert Path(session_name) == data_dir / "sessions" / "session_12025551234"
    assert Path(f"{session_name}.session").read_text(encoding="utf-8") == "legacy"
    assert not (tmp_path / "session_12025551234.session").exists()

    AccountManager.clear_instance()


def test_forward_store_keeps_latest_500_records(tmp_path):
    store = ForwardStore(tmp_path / "forward.db")
    message = make_message(MessageSender(1))

    for index in range(505):
        message.message_id = index
        store.add("acc", message, 99, False, {})

    rows = store.list(limit=600)

    assert len(rows) == 500
    assert rows[0]["source_message_id"] == 504
    assert rows[-1]["source_message_id"] == 5


def test_forward_store_marks_result_and_restores_message(tmp_path):
    store = ForwardStore(tmp_path / "forward.db")
    message = make_album_message(grouped_id=555)
    record_id = store.add("acc", message, 99, True, {"enabled": True})

    store.mark_result(record_id, False, "AI失败")
    record = store.get(record_id)
    restored = store.message_from_record(record)

    assert record["status"] == "failed"
    assert record["attempts"] == 1
    assert record["last_error"] == "AI失败"
    assert restored.message_id == message.message_id
    assert restored.grouped_id == 555
    assert store.rewrite_options(record) == {"enabled": True}


def test_forward_store_ignores_invalid_rewrite_options_json(tmp_path):
    import sqlite3

    store = ForwardStore(tmp_path / "forward.db")
    record_id = store.add("acc", make_message(MessageSender(1)), 99, False, {"enabled": True})
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE forward_records SET rewrite_options = ? WHERE id = ?", ("{bad json", record_id))

    assert store.rewrite_options(store.get(record_id)) == {}


def test_merge_actions_keep_highest_priority_rewrite_template():
    MonitorEngine.clear_instance()
    engine = MonitorEngine()
    actions = {
        "forward_targets": set(),
        "enhanced_forward": False,
        "forward_rewrite": {},
        "forward_rewrite_by_target": {},
        "email_notify": False,
        "log_files": set(),
        "reply_enabled": False,
        "reply_texts": [],
        "reply_delay_min": 0,
        "reply_delay_max": 0,
        "reply_mode": "reply",
        "reply_content_type": "custom",
        "ai_reply_prompt": "",
        "custom_actions": []
    }
    high = DummyMonitor(BaseMonitorConfig(
        auto_forward=True,
        forward_targets=[1],
        forward_rewrite_enabled=True,
        forward_rewrite_template="高优先级{topic}"
    ))
    low = DummyMonitor(BaseMonitorConfig(
        auto_forward=True,
        forward_targets=[2],
        forward_rewrite_enabled=True,
        forward_rewrite_template="低优先级{topic}"
    ))

    engine._merge_monitor_actions(high, "high", actions)
    engine._merge_monitor_actions(low, "low", actions)

    assert actions["forward_targets"] == {1, 2}
    assert actions["forward_rewrite"]["template"] == "高优先级{topic}"
    assert actions["forward_rewrite_by_target"][1]["template"] == "高优先级{topic}"
    assert actions["forward_rewrite_by_target"][2]["template"] == "低优先级{topic}"
    MonitorEngine.clear_instance()


def test_merge_actions_keep_rewrite_options_per_target():
    MonitorEngine.clear_instance()
    engine = MonitorEngine()
    actions = {
        "forward_targets": set(),
        "enhanced_forward": False,
        "forward_rewrite": {},
        "forward_rewrite_by_target": {},
        "email_notify": False,
        "log_files": set(),
        "reply_enabled": False,
        "reply_texts": [],
        "reply_delay_min": 0,
        "reply_delay_max": 0,
        "reply_mode": "reply",
        "reply_content_type": "custom",
        "ai_reply_prompt": "",
        "custom_actions": []
    }
    with_rewrite = DummyMonitor(BaseMonitorConfig(
        auto_forward=True,
        forward_targets=[1],
        forward_rewrite_enabled=True,
        forward_rewrite_template="模板{topic}"
    ))
    without_rewrite = DummyMonitor(BaseMonitorConfig(
        auto_forward=True,
        forward_targets=[2],
        forward_rewrite_enabled=False
    ))

    engine._merge_monitor_actions(with_rewrite, "with_rewrite", actions)
    engine._merge_monitor_actions(without_rewrite, "without_rewrite", actions)

    assert actions["forward_rewrite_by_target"][1]["template"] == "模板{topic}"
    assert actions["forward_rewrite_by_target"][2] == {}
    MonitorEngine.clear_instance()


def test_engine_does_not_forward_when_auto_forward_is_string_false():
    MonitorEngine.clear_instance()
    engine = MonitorEngine()
    monitor = DummyMonitor(BaseMonitorConfig(
        auto_forward="false",
        forward_targets=[99],
        enhanced_forward="true",
        forward_rewrite_enabled="true"
    ))

    actions = engine._collect_actions(monitor, "dummy")

    assert actions["forward_targets"] == set()
    assert actions["enhanced_forward"] is False
    assert actions["forward_rewrite"] == {}
    assert actions["forward_rewrite_by_target"] == {}
    MonitorEngine.clear_instance()


def test_web_schedule_validation_accepts_cron_and_interval():
    assert WebApp._validate_schedule("cron", "0 9 * * *") is None
    assert WebApp._validate_schedule("interval", "1 30") == (1, 30)


def test_web_schedule_validation_rejects_invalid_interval():
    for expr in ("", "1", "0 0", "-1 10", "1 60", "a b"):
        try:
            WebApp._validate_schedule("interval", expr)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"invalid interval accepted: {expr}")
