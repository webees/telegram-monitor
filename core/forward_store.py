"""
SQLite-backed forward records with bounded retention.
"""

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model import MessageMedia, MessageSender, TelegramMessage, get_data_dir


class ForwardStore:
    MAX_RECORDS = 500

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else get_data_dir() / "forward_queue.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forward_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    source_chat_id INTEGER NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    grouped_id INTEGER,
                    target_id INTEGER NOT NULL,
                    enhanced_forward INTEGER NOT NULL,
                    rewrite_options TEXT NOT NULL,
                    message_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_forward_status ON forward_records(status, id)")

    def add(
        self,
        account_id: str,
        message: TelegramMessage,
        target_id: int,
        enhanced_forward: bool,
        rewrite_options: Optional[Dict[str, Any]] = None
    ) -> int:
        now = self._now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO forward_records (
                    created_at, updated_at, account_id, source_chat_id, source_message_id,
                    grouped_id, target_id, enhanced_forward, rewrite_options, message_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                now, now, account_id, message.chat_id, message.message_id, message.grouped_id,
                target_id, int(enhanced_forward), json.dumps(rewrite_options or {}, ensure_ascii=False),
                json.dumps(self.message_to_dict(message), ensure_ascii=False)
            ))
            self._trim(conn)
            return int(cursor.lastrowid)

    def mark_result(self, record_id: int, success: bool, error: str = ""):
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE forward_records
                SET updated_at = ?, status = ?, attempts = attempts + 1, last_error = ?
                WHERE id = ?
            """, (self._now(), "success" if success else "failed", error or "", record_id))

    def get(self, record_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM forward_records WHERE id = ?", (record_id,)).fetchone()
            return self._row(row) if row else None

    def list(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 100), self.MAX_RECORDS))
        sql = "SELECT * FROM forward_records"
        params: List[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [self._row(row) for row in conn.execute(sql, params).fetchall()]

    def message_from_record(self, record: Dict[str, Any]) -> TelegramMessage:
        data = json.loads(record.get("message_json") or "{}")
        sender = MessageSender(**data.get("sender", {"id": 0}))
        media = data.get("media")
        return TelegramMessage(
            message_id=data.get("message_id", record["source_message_id"]),
            chat_id=data.get("chat_id", record["source_chat_id"]),
            sender=sender,
            text=data.get("text", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            media=MessageMedia(**media) if media else None,
            is_forwarded=data.get("is_forwarded", False),
            forward_from_channel_id=data.get("forward_from_channel_id"),
            reply_to_message_id=data.get("reply_to_message_id"),
            grouped_id=data.get("grouped_id")
        )

    @staticmethod
    def message_to_dict(message: TelegramMessage) -> Dict[str, Any]:
        return {
            "message_id": message.message_id,
            "chat_id": message.chat_id,
            "sender": asdict(message.sender) if message.sender else {"id": 0},
            "text": message.text,
            "timestamp": message.timestamp.isoformat(),
            "media": asdict(message.media) if message.media else None,
            "is_forwarded": message.is_forwarded,
            "forward_from_channel_id": message.forward_from_channel_id,
            "reply_to_message_id": message.reply_to_message_id,
            "grouped_id": message.grouped_id
        }

    @staticmethod
    def rewrite_options(record: Dict[str, Any]) -> Dict[str, Any]:
        try:
            options = json.loads(record.get("rewrite_options") or "{}")
            return options if isinstance(options, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["enhanced_forward"] = bool(data["enhanced_forward"])
        return data

    def _trim(self, conn):
        conn.execute("""
            DELETE FROM forward_records
            WHERE id NOT IN (
                SELECT id FROM forward_records ORDER BY id DESC LIMIT ?
            )
        """, (self.MAX_RECORDS,))
