from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_seeded_demo_has_three_distinct_outcomes(monkeypatch):
    # Demo must stay deterministic and never spend external LLM tokens even
    # when the deployed Live policy requires the ensemble.
    monkeypatch.setenv("ENSEMBLE_REQUIRED", "true")
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
        assert result["pipeline"]["feedback_applied"] == 0
        assert "frozen deterministic decision path" in " ".join(result["limitations"])


def test_close_pair_demo_packs_return_real_evidence():
    response = client.post(
        "/api/analyze",
        json={
            "disease": "Atopic dermatitis",
            "genes": ["IL13", "S100A9"],
            "tissue": "skin",
            "mode": "demo",
        },
    )
    assert response.status_code == 200
    verdicts = {item["gene"]: item for item in response.json()["results"]}
    assert verdicts["IL13"]["verdict"] == "Driver"
    assert len(verdicts["IL13"]["evidence"]) >= 4
    assert verdicts["S100A9"]["verdict"] == "Passenger"
    assert len(verdicts["S100A9"]["evidence"]) >= 3

    psoriasis = client.post(
        "/api/analyze",
        json={
            "disease": "Psoriasis",
            "genes": ["TYK2", "STAT3"],
            "tissue": "skin",
            "mode": "demo",
        },
    )
    assert psoriasis.status_code == 200
    rows = {item["gene"]: item for item in psoriasis.json()["results"]}
    assert rows["TYK2"]["verdict"] == "Driver"
    assert len(rows["TYK2"]["evidence"]) >= 3
    assert rows["STAT3"]["verdict"] == "Insufficient evidence"
    assert len(rows["STAT3"]["evidence"]) >= 3
