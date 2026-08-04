from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_seeded_demo_has_three_distinct_outcomes(monkeypatch):
    # Unit/API tests must stay deterministic and never spend external LLM tokens.
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ENSEMBLE_REQUIRED", "false")
    response = client.get("/api/demo")
    assert response.status_code == 200
    payload = response.json()
    verdicts = {item["gene"]: item["verdict"] for item in payload["results"]}
    assert verdicts == {
        "IL4R": "Driver",
        "FLG": "Insufficient evidence",
        "S100A8": "Passenger",
    }
    for result in payload["results"]:
        assert result["research_use_only"] is True
        assert all(item["source_url"] for item in result["evidence"])
