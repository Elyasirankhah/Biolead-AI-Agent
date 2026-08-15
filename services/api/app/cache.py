from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

_redis_client: Any | None = None
_redis_enabled: bool | None = None
_default_cache: "EvidenceCache | None" = None


def redis_url() -> str | None:
    url = os.getenv("REDIS_URL", "").strip()
    return url or None


def _ttl_seconds() -> int:
    raw = os.getenv("REDIS_TTL_SECONDS", "").strip()
    if raw.isdigit():
        return max(60, int(raw))
    hours = os.getenv("CACHE_TTL_HOURS", "24").strip()
    try:
        return max(60, int(float(hours) * 3600))
    except ValueError:
        return 24 * 3600


def connect_redis() -> None:
    """Best-effort Redis connect. API stays up if Redis is missing."""
    global _redis_client, _redis_enabled
    url = redis_url()
    if not url:
        _redis_client = None
        _redis_enabled = False
        return
    try:
        import redis

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
        client.ping()
        _redis_client = client
        _redis_enabled = True
    except Exception:
        _redis_client = None
        _redis_enabled = False


def close_redis() -> None:
    global _redis_client, _redis_enabled, _default_cache
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
    _redis_client = None
    _redis_enabled = False
    _default_cache = None


def redis_status() -> dict[str, Any]:
    if not redis_url():
        return {"enabled": False, "status": "disabled", "detail": "REDIS_URL not set", "backend": "memory"}
    if _redis_client is None or not _redis_enabled:
        return {
            "enabled": True,
            "status": "disconnected",
            "detail": "fallback to in-memory cache",
            "backend": "memory",
        }
    try:
        _redis_client.ping()
        return {"enabled": True, "status": "ok", "backend": "redis"}
    except Exception as exc:  # noqa: BLE001
        return {"enabled": True, "status": "error", "detail": str(exc), "backend": "memory"}


class EvidenceCache:
    """Source cache: Redis when available, else instance-local memory."""

    def __init__(self, ttl_hours: int | None = None) -> None:
        if ttl_hours is None:
            self.ttl = timedelta(seconds=_ttl_seconds())
        else:
            self.ttl = timedelta(hours=ttl_hours)
        self.prefix = os.getenv("REDIS_PREFIX", "biolead:evidence:").strip() or "biolead:evidence:"
        self._local: dict[str, tuple[datetime, Any]] = {}

    def get(self, key: str) -> Any | None:
        full = f"{self.prefix}{key}"
        if _redis_client is not None and _redis_enabled:
            try:
                raw = _redis_client.get(full)
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception:
                pass
        cached = self._local.get(full)
        if not cached or datetime.now(timezone.utc) - cached[0] > self.ttl:
            self._local.pop(full, None)
            return None
        return cached[1]

    def set(self, key: str, value: Any) -> None:
        full = f"{self.prefix}{key}"
        self._local[full] = (datetime.now(timezone.utc), value)
        if _redis_client is not None and _redis_enabled:
            try:
                _redis_client.setex(full, int(self.ttl.total_seconds()), json.dumps(value))
            except Exception:
                pass


def get_evidence_cache() -> EvidenceCache:
    """Process-wide cache for Live adapters (shares memory + Redis)."""
    global _default_cache
    if _default_cache is None:
        _default_cache = EvidenceCache()
    return _default_cache
