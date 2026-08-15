from app.fixtures import get_demo_evidence
from app.ledger import build_decision_ledger
from app.scoring import score_evidence


def test_decision_ledger_for_demo_il4r():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    scorecard, verdict, _ = score_evidence(items)
    ledger = build_decision_ledger(
        gene="IL4R",
        disease="Atopic dermatitis",
        tissue="skin",
        verdict=verdict,
        direction="inhibit",
        items=items,
        scorecard=scorecard,
        mode="demo",
    )
    assert ledger.hypothesis.startswith("Reducing IL4R")
    assert ledger.falsification.status in {"PASSED", "UNRESOLVED"}
    assert ledger.evidence_for
    assert ledger.what_would_change
    assert ledger.content_hash
    assert ledger.snapshot_id.startswith("BL-IL4R-")
    assert ledger.reproducible is True


def test_decision_ledger_passenger_has_counter_path():
    items = get_demo_evidence("Atopic dermatitis", "S100A8")
    scorecard, verdict, _ = score_evidence(items)
    ledger = build_decision_ledger(
        gene="S100A8",
        disease="Atopic dermatitis",
        tissue="skin",
        verdict=verdict,
        direction="unresolved",
        items=items,
        scorecard=scorecard,
        mode="demo",
    )
    assert verdict == "Passenger"
    assert ledger.evidence_against
    assert ledger.falsification.strongest_counter_evidence_id
    assert ledger.falsification.gate_completed is True
