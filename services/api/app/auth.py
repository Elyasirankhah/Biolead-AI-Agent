from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient


@dataclass
class AuthUser:
    id: str
    email: str | None = None


def _supabase_url() -> str:
    return (
        os.getenv("SUPABASE_URL", "").strip()
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    )


def _jwks_url() -> str:
    explicit = os.getenv("SUPABASE_JWKS_URL", "").strip()
    if explicit:
        return explicit
    base = _supabase_url().rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json" if base else ""


def auth_configured() -> bool:
    return bool(os.getenv("SUPABASE_JWT_SECRET", "").strip() or _jwks_url())


def auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "false").strip().lower() in {"1", "true", "yes"}


@lru_cache(maxsize=1)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


def _user_from_payload(payload: dict[str, Any]) -> AuthUser:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")
    return AuthUser(id=str(user_id), email=payload.get("email"))


def _decode_with_secret(token: str, secret: str) -> AuthUser:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience="authenticated",
    )
    return _user_from_payload(payload)


def _decode_with_jwks(token: str, jwks_url: str) -> AuthUser:
    signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
    )
    return _user_from_payload(payload)


def _decode_token(token: str) -> AuthUser:
    secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
    jwks = _jwks_url()
    if not secret and not jwks:
        raise HTTPException(status_code=503, detail="Supabase auth is not configured")

    errors: list[str] = []
    if jwks:
        try:
            return _decode_with_jwks(token, jwks)
        except Exception as exc:  # noqa: BLE001 - surface decode failures cleanly
            errors.append(f"jwks: {exc}")
    if secret:
        try:
            return _decode_with_secret(token, secret)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"secret: {exc}")
    detail = "; ".join(errors) if errors else "Unable to verify token"
    raise HTTPException(status_code=401, detail=f"Invalid auth token: {detail}")


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser | None:
    """Guest-friendly auth. If a Bearer token is present, verify it."""
    if not authorization:
        if auth_required() and auth_configured():
            raise HTTPException(status_code=401, detail="Sign in required")
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Expected Bearer token")
    return _decode_token(token)


OptionalUser = Annotated[AuthUser | None, Depends(get_optional_user)]
