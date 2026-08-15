import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app


def _token(sub: str = "user-123", email: str = "sci@oddity.test") -> str:
    return jwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated", "role": "authenticated"},
        "test-secret-for-biolead-auth-32b!",
        algorithm="HS256",
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-for-biolead-auth-32b!")
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ENSEMBLE_REQUIRED", "false")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    return TestClient(app)


def test_health_reports_auth(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["auth"]["supabase_configured"] is True
    assert body["auth"]["required"] is False


def test_analyze_accepts_bearer(client: TestClient):
    res = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "disease": "Atopic dermatitis",
            "genes": ["IL4R"],
            "tissue": "skin",
            "mode": "demo",
        },
    )
    assert res.status_code == 200
    assert res.json()["results"][0]["gene"] == "IL4R"


def test_invalid_token_rejected(client: TestClient):
    res = client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer not-a-jwt"},
        json={
            "disease": "Atopic dermatitis",
            "genes": ["IL4R"],
            "tissue": "skin",
            "mode": "demo",
        },
    )
    assert res.status_code == 401


def test_optional_chat_ignores_bearer_when_supabase_env_blank(monkeypatch: pytest.MonkeyPatch):
    from fastapi import HTTPException
    from app import auth as auth_mod

    def unconfigured(_token: str):
        raise HTTPException(status_code=503, detail="Supabase auth is not configured")

    monkeypatch.setattr(auth_mod, "_decode_token", unconfigured)
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ENSEMBLE_REQUIRED", "false")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    with TestClient(app) as client:
        res = client.post(
            "/api/chat",
            headers={"Authorization": "Bearer not-configured"},
            json={
                "run_id": "auth-probe",
                "messages": [{"role": "user", "content": "let's try a close pair with the same disease"}],
                "context": {
                    "disease": "Atopic dermatitis",
                    "dossier": {"gene": "IL4R", "verdict": "Driver"},
                    "session": [{"gene": "IL4R"}, {"gene": "FLG"}, {"gene": "S100A8"}],
                },
            },
        )
        assert res.status_code == 200
        assert "IL13" in res.json()["reply"]


def test_auth_required_blocks_guest(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-for-biolead-auth-32b!")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ENSEMBLE_REQUIRED", "false")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    with TestClient(app) as client:
        res = client.post(
            "/api/analyze",
            json={
                "disease": "Atopic dermatitis",
                "genes": ["IL4R"],
                "tissue": "skin",
                "mode": "demo",
            },
        )
        assert res.status_code == 401
