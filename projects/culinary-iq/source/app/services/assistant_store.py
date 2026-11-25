from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings


DB_PATH = settings.data_root / settings.restaurant_directory_filename
MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "013_culinary_iq_assistant.sql"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as db:
        db.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?, ?)", ("013_culinary_iq_assistant", _now()))
        db.commit()


def _message(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["navigation"] = json.loads(value.pop("navigation_json") or "[]")
    value["source_refs"] = json.loads(value.pop("source_refs_json") or "[]")
    value.pop("workspace_id", None)
    value.pop("context_json", None)
    value.pop("tool_calls_json", None)
    value.pop("selected_restaurant_id", None)
    value.pop("selected_location_id", None)
    value.pop("route_context", None)
    value.pop("provider", None)
    value.pop("prompt_tokens", None)
    value.pop("completion_tokens", None)
    value.pop("correlation_id", None)
    return value


def _conversation(row: sqlite3.Row, messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {**dict(row), "archived": bool(row["archived"]), "messages": messages or []}


def create_conversation(workspace_id: str, title: str | None, context: dict[str, Any]) -> dict[str, Any]:
    initialize()
    conversation_id, created = str(uuid4()), _now()
    with closing(_connect()) as db:
        db.execute(
            "INSERT INTO assistant_conversations VALUES (?,?,?,?,?,?,?,?,?)",
            (conversation_id, workspace_id, title, context.get("selected_restaurant_id"), context.get("selected_location_id"), context.get("current_route"), 0, created, created),
        )
        db.commit()
        row = db.execute("SELECT * FROM assistant_conversations WHERE id=?", (conversation_id,)).fetchone()
    return _conversation(row)


def list_conversations(workspace_id: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    initialize()
    with closing(_connect()) as db:
        rows = db.execute(
            "SELECT * FROM assistant_conversations WHERE workspace_id=? AND archived=0 ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (workspace_id, min(max(limit, 1), 50), max(offset, 0)),
        ).fetchall()
    return [_conversation(row) for row in rows]


def get_conversation(conversation_id: str, workspace_id: str, history_limit: int = 50) -> dict[str, Any] | None:
    initialize()
    with closing(_connect()) as db:
        row = db.execute("SELECT * FROM assistant_conversations WHERE id=? AND workspace_id=?", (conversation_id, workspace_id)).fetchone()
        if not row:
            return None
        messages = db.execute(
            "SELECT * FROM (SELECT * FROM assistant_messages WHERE conversation_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?) ORDER BY created_at",
            (conversation_id, workspace_id, min(max(history_limit, 1), 100)),
        ).fetchall()
    return _conversation(row, [_message(item) for item in messages])


def get_provider_history(conversation_id: str, workspace_id: str, limit: int) -> list[dict[str, str]]:
    initialize()
    with closing(_connect()) as db:
        rows = db.execute(
            "SELECT role,content FROM (SELECT role,content,created_at FROM assistant_messages WHERE conversation_id=? AND workspace_id=? AND response_status='complete' ORDER BY created_at DESC LIMIT ?) ORDER BY created_at",
            (conversation_id, workspace_id, min(max(limit, 2), 100)),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def add_message(
    conversation_id: str, workspace_id: str, role: str, content: str, context: dict[str, Any], status: str,
    correlation_id: str, *, model: str | None = None, tool_calls: list[dict[str, Any]] | None = None,
    source_refs: list[dict[str, Any]] | None = None, navigation: list[dict[str, str]] | None = None,
    prompt_tokens: int | None = None, completion_tokens: int | None = None,
) -> dict[str, Any]:
    initialize()
    message_id, created = str(uuid4()), _now()
    with closing(_connect()) as db:
        exists = db.execute("SELECT 1 FROM assistant_conversations WHERE id=? AND workspace_id=?", (conversation_id, workspace_id)).fetchone()
        if not exists:
            raise KeyError(conversation_id)
        db.execute(
            "INSERT INTO assistant_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (message_id, conversation_id, workspace_id, role, content, context.get("selected_restaurant_id"), context.get("selected_location_id"), context.get("current_route"), json.dumps(context), json.dumps(tool_calls or []), json.dumps(source_refs or []), json.dumps(navigation or []), status, "openai" if model else None, model, prompt_tokens, completion_tokens, correlation_id, created),
        )
        title = None
        if role == "user":
            title = " ".join(content.strip().split())[:80]
        db.execute(
            "UPDATE assistant_conversations SET selected_restaurant_id=?,selected_location_id=?,route_context=?,updated_at=?,title=COALESCE(title,?) WHERE id=? AND workspace_id=?",
            (context.get("selected_restaurant_id"), context.get("selected_location_id"), context.get("current_route"), created, title, conversation_id, workspace_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM assistant_messages WHERE id=?", (message_id,)).fetchone()
    return _message(row)


def archive_conversation(conversation_id: str, workspace_id: str) -> bool:
    initialize()
    with closing(_connect()) as db:
        result = db.execute("UPDATE assistant_conversations SET archived=1,updated_at=? WHERE id=? AND workspace_id=?", (_now(), conversation_id, workspace_id))
        db.commit()
    return bool(result.rowcount)


def update_conversation_context(conversation_id: str, workspace_id: str, context: dict[str, Any]) -> bool:
    initialize()
    with closing(_connect()) as db:
        result = db.execute(
            """UPDATE assistant_conversations
               SET selected_restaurant_id=?,selected_location_id=?,route_context=?,updated_at=?
               WHERE id=? AND workspace_id=? AND archived=0""",
            (
                context.get("selected_restaurant_id"), context.get("selected_location_id"),
                context.get("current_route"), _now(), conversation_id, workspace_id,
            ),
        )
        db.commit()
    return bool(result.rowcount)


def audit_tool(workspace_id: str, conversation_id: str, correlation_id: str, tool_name: str, argument_keys: list[str], status: str, result_summary: dict[str, Any], duration_ms: int, message_id: str | None = None) -> None:
    initialize()
    with closing(_connect()) as db:
        db.execute(
            "INSERT INTO assistant_tool_audit VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), workspace_id, conversation_id, message_id, correlation_id, tool_name, json.dumps(sorted(argument_keys)), status, json.dumps(result_summary), duration_ms, _now()),
        )
        db.commit()


initialize()
