from __future__ import annotations

import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def mongodb_uri() -> str | None:
    uri = os.getenv("MONGODB_URI", "").strip()
    return uri or None


def mongodb_db_name() -> str:
    return os.getenv("MONGODB_DB", "biolead").strip() or "biolead"


async def connect_mongo() -> None:
    """Connect if MONGODB_URI is set; otherwise keep API offline-safe."""
    global _client, _db
    uri = mongodb_uri()
    if not uri:
        _client = None
        _db = None
        return
    _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    # Fail fast on bad URI during startup when possible.
    await _client.admin.command("ping")
    _db = _client[mongodb_db_name()]
    await _db.runs.create_index("run_id", unique=True)
    await _db.runs.create_index([("created_at", -1)])
    await _db.runs.create_index("disease")
    await _db.runs.create_index("user_id")
    await _db.feedback.create_index("feedback_id", unique=True)
    await _db.feedback.create_index([("disease_norm", 1), ("gene", 1), ("evidence_id", 1), ("created_at", -1)])
    try:
        await _db.chat_sessions.drop_index("user_id_1_run_id_1")
    except Exception:
        pass
    await _db.chat_sessions.create_index(
        [("user_id", 1), ("chat_id", 1)],
        unique=True,
        partialFilterExpression={"chat_id": {"$type": "string"}},
    )
    await _db.chat_sessions.create_index([("user_id", 1), ("updated_at", -1)])


async def close_mongo() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def get_db() -> AsyncIOMotorDatabase | None:
    return _db


async def mongo_status() -> dict[str, Any]:
    if not mongodb_uri():
        return {"enabled": False, "status": "disabled", "detail": "MONGODB_URI not set"}
    if _db is None or _client is None:
        return {"enabled": True, "status": "disconnected", "detail": "client not initialized"}
    try:
        await _client.admin.command("ping")
        return {"enabled": True, "status": "ok", "database": mongodb_db_name()}
    except Exception as exc:  # noqa: BLE001 - surface connection errors in health
        return {"enabled": True, "status": "error", "detail": str(exc)}
