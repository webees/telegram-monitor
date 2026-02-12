"""core/validator + monitor/keyword 单元测试"""
import pytest
from core.validator import (
    validate_phone, validate_chat_id, validate_api_credentials,
    validate_email, validate_cron_expression,
)
from monitor.keyword import KeywordMatchStrategy


# ── validate_phone ──

class TestPhone:
    @pytest.mark.parametrize("phone", [
        "+8613800138000",
        "+12025551234",
        "+441234567890",
    ])
    def test_valid(self, phone):
        assert validate_phone(phone) is True

    @pytest.mark.parametrize("phone,reason", [
        ("",            "empty"),
        ("13800138000", "no plus"),
        ("+123",        "too short"),
        ("+1234567890123456", "too long"),
        ("+86-138-0013", "has dashes"),
        ("+86abc",       "has letters"),
    ])
    def test_invalid(self, phone, reason):
        assert validate_phone(phone) is False, reason


# ── validate_chat_id ──

class TestChatId:
    @pytest.mark.parametrize("chat_id", [0, 123, -100123456789, "456"])
    def test_valid(self, chat_id):
        assert validate_chat_id(chat_id) is True

    @pytest.mark.parametrize("chat_id", ["abc", None, "", 10**12])
    def test_invalid(self, chat_id):
        assert validate_chat_id(chat_id) is False


# ── validate_api_credentials ──

class TestApiCredentials:
    VALID_HASH = "a" * 32

    def test_valid(self):
        assert validate_api_credentials(12345, self.VALID_HASH) is True
        assert validate_api_credentials("12345", self.VALID_HASH) is True

    @pytest.mark.parametrize("api_id,api_hash,reason", [
        ("abc",  "a" * 32, "non-numeric id"),
        (123,    "",        "empty hash"),
        (123,    "short",   "hash too short"),
        (123,    "g" * 32,  "invalid hex chars"),
        (None,   "a" * 32,  "None id"),
    ])
    def test_invalid(self, api_id, api_hash, reason):
        assert validate_api_credentials(api_id, api_hash) is False, reason


# ── validate_email ──

class TestEmail:
    @pytest.mark.parametrize("email", [
        "user@example.com",
        "test.name+tag@domain.org",
        "a@b.co",
    ])
    def test_valid(self, email):
        assert validate_email(email) is True

    @pytest.mark.parametrize("email", ["", "no-at-sign", "@no-user.com", "user@.com"])
    def test_invalid(self, email):
        assert validate_email(email) is False


# ── validate_cron_expression ──

class TestCron:
    @pytest.mark.parametrize("cron", [
        "0 9 * * *",
        "*/15 * * * *",
        "30 18 * * 1",
        "0 0 1 1 *",
    ])
    def test_valid(self, cron):
        ok, msg = validate_cron_expression(cron)
        assert ok is True, msg

    @pytest.mark.parametrize("cron,reason", [
        ("",              "empty"),
        ("0 9 *",         "too few parts"),
        ("0 9 * * * *",   "too many parts"),
        ("0 25 * * *",    "hour > 23"),
        ("60 0 * * *",    "minute > 59"),
    ])
    def test_invalid(self, cron, reason):
        ok, _ = validate_cron_expression(cron)
        assert ok is False, reason


# ── KeywordMatchStrategy ──

class TestKeywordMatch:
    def test_exact_match(self):
        match = KeywordMatchStrategy.exact_match
        assert match("hello", "hello") is True
        assert match("Hello", "hello") is True       # case insensitive
        assert match(" hello ", "hello") is True      # strips whitespace
        assert match("hello world", "hello") is False # not exact

    def test_partial_match(self):
        match = KeywordMatchStrategy.partial_match
        assert match("hello world", "hello") is True
        assert match("say HELLO!", "hello") is True   # case insensitive
        assert match("hi there", "hello") is False

    def test_regex_match(self):
        match = KeywordMatchStrategy.regex_match
        assert match("code: 123456", r"\d{6}") is True
        assert match("no digits here", r"\d{6}") is False
        assert match("hello", r"[invalid") is False   # bad regex => False

    def test_get_strategy(self):
        from core.model import MatchType
        fn = KeywordMatchStrategy.get_match_function(MatchType.EXACT)
        assert fn("hello", "hello") is True
        assert fn("hello world", "hello") is False
