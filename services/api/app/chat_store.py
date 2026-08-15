from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import get_db

_MEMORY_CHATS: dict[tuple[str, str], dict[str, Any]] = {}


def _key(user_id: str, chat_id: str) -> tuple[str, str]:
    return user_id.strip(), chat_id.strip()


def _clean_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for message in messages[-40:]:
        role = str(message.get("role") or "user")
        if role not in {"user", "assistant", "command"}:
            continue
        item: dict[str, Any] = {
            "role": role,
            "content": str(message.get("content") or "")[:8000],
        }
        sources = message.get("sources")
        if isinstance(sources, list) and sources:
            item["sources"] = sources[:8]
        command = message.get("command")
        if isinstance(command, dict) and command:
            item["command"] = command
        if role == "command" and not item.get("command") and not item["content"]:
            continue
        if role != "command" and not item["content"]:
            continue
        cleaned.append(item)
    return cleaned


def _title(messages: list[dict[str, Any]], disease: str) -> str:
    for message in messages:
        if message.get("role") == "user" and message.get("content"):
            text = " ".join(str(message["content"]).split())
            return (text[:56] + "…") if len(text) > 56 else text
    return f"{disease or 'Clara'} session"


def _preview(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") in {"user", "assistant"} and message.get("content"):
            text = " ".join(str(message["content"]).split())
            return (text[:80] + "…") if len(text) > 80 else text
    return ""


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value or "")


def _summary(document: dict[str, Any]) -> dict[str, Any]:
    chat_id = str(document.get("chat_id") or document.get("run_id") or "")
    return {
        "chat_id": chat_id,
        "run_id": str(document.get("run_id") or ""),
        "title": str(document.get("title") or "Clara session"),
        "preview": str(document.get("preview") or ""),
        "disease": str(document.get("disease") or ""),
        "updated_at": _iso(document.get("updated_at")),
    }


async def save_chat_turn(
    *,
    user_id: str,
    user_email: str | None,
    run_id: str,
    disease: str,
    messages: list[dict[str, Any]],
    chat_id: str | None = None,
) -> bool:
    """Persist a signed-in user's Clara conversation."""
    now = datetime.now(timezone.utc)
    clean_messages = _clean_messages(messages)
    cid = (chat_id or run_id).strip()
    document = {
        "user_id": user_id,
        "user_email": user_email,
        "chat_id": cid,
        "run_id": run_id,
        "disease": disease,
        "title": _title(clean_messages, disease),
        "preview": _preview(clean_messages),
        "messages": clean_messages,
        "updated_at": now,
    }
    db = get_db()
    if db is None:
        stored = dict(document)
        existing = _MEMORY_CHATS.get(_key(user_id, cid))
        stored["created_at"] = (existing or {}).get("created_at") or now
        _MEMORY_CHATS[_key(user_id, cid)] = stored
        return False
    await db.chat_sessions.update_one(
        {"user_id": user_id, "chat_id": cid},
        {
            "$set": document,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return True


async def load_chat_history(
    *,
    user_id: str,
    run_id: str | None = None,
    chat_id: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return conversation history and whether it came from durable Mongo storage."""
    cid = (chat_id or run_id or "").strip()
    if not cid:
        return [], False
    db = get_db()
    if db is None:
        document = _MEMORY_CHATS.get(_key(user_id, cid))
        return list((document or {}).get("messages", [])), False
    document = await db.chat_sessions.find_one(
        {
            "user_id": user_id,
            "$or": [{"chat_id": cid}, {"chat_id": {"$exists": False}, "run_id": cid}],
        },
        {"_id": 0, "messages": 1},
    )
    return list((document or {}).get("messages", [])), True


async def list_chat_sessions(*, user_id: str, limit: int = 40) -> tuple[list[dict[str, Any]], bool]:
    db = get_db()
    if db is None:
        rows = [doc for (uid, _cid), doc in _MEMORY_CHATS.items() if uid == user_id]
        rows.sort(key=lambda item: item.get("updated_at") or datetime.min, reverse=True)
        return [_summary(item) for item in rows[:limit]], False
    cursor = (
        db.chat_sessions.find(
            {"user_id": user_id},
            {"_id": 0, "messages": 0},
        )
        .sort("updated_at", -1)
        .limit(limit)
    )
    return [_summary(item) async for item in cursor], True


async def delete_chat_session(*, user_id: str, chat_id: str) -> bool:
    cid = chat_id.strip()
    db = get_db()
    if db is None:
        return _MEMORY_CHATS.pop(_key(user_id, cid), None) is not None
    result = await db.chat_sessions.delete_one(
        {
            "user_id": user_id,
            "$or": [{"chat_id": cid}, {"chat_id": {"$exists": False}, "run_id": cid}],
        }
    )
    return result.deleted_count > 0


def clear_memory_chats() -> None:
    _MEMORY_CHATS.clear()
