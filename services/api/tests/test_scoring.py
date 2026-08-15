from app.fixtures import get_demo_evidence
from app.reasoning import _ground_generated_narrative
from app.scoring import score_evidence


def test_il4r_is_driver_with_convergent_evidence():
    scorecard, verdict, confidence = score_evidence(
        get_demo_evidence("Atopic dermatitis", "IL4R")
    )
    assert verdict == "Driver"
    assert scorecard.independent_pillars >= 3
    assert scorecard.causality.value >= 58
    assert confidence >= 70


def test_flg_abstains_despite_strong_genetics():
    scorecard, verdict, _ = score_evidence(
        get_demo_evidence("Atopic dermatitis", "FLG")
    )
    assert verdict == "Insufficient evidence"
    assert scorecard.evidence_quality.value >= 50
    assert scorecard.actionability.value < 60


def test_s100a8_is_passenger_like_with_counterevidence():
    scorecard, verdict, _ = score_evidence(
        get_demo_evidence("Atopic dermatitis", "S100A8")
    )
    assert verdict == "Passenger"
    assert scorecard.contradiction_penalty > 0
    assert scorecard.causality.value < 32


def test_il13_close_pair_is_driver_with_clinical_rescue():
    scorecard, verdict, confidence = score_evidence(
        get_demo_evidence("Atopic dermatitis", "IL13")
    )
    assert verdict == "Driver"
    assert scorecard.independent_pillars >= 3
    assert confidence >= 70


def test_s100a9_close_pair_is_passenger_like():
    scorecard, verdict, _ = score_evidence(
        get_demo_evidence("Atopic dermatitis", "S100A9")
    )
    assert verdict == "Passenger"
    assert scorecard.contradiction_penalty > 0


def test_psoriasis_tyk2_is_driver():
    _, verdict, _ = score_evidence(get_demo_evidence("Psoriasis", "TYK2"))
    assert verdict == "Driver"


def test_psoriasis_stat3_abstains_without_clinical_rescue():
    scorecard, verdict, _ = score_evidence(get_demo_evidence("Psoriasis", "STAT3"))
    assert verdict == "Insufficient evidence"
    assert scorecard.evidence_count >= 3
    assert any(item.stance == "contradicts" for item in get_demo_evidence("Psoriasis", "STAT3"))
    scorecard, verdict, confidence = score_evidence([])
    assert verdict == "Insufficient evidence"
    assert scorecard.evidence_quality.value == 0
    assert confidence <= 69


def test_llm_claim_lists_cannot_add_uncited_claims():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    fallback = {
        "executive_summary": "fallback",
        "driver_case": ["fallback driver"],
        "passenger_case": ["fallback counter"],
        "next_experiments": ["Perform an orthogonal perturbation experiment."],
    }
    generated = {
        "executive_summary": "grounded synthesis",
        "driver_case": [items[0].title, "Invented causal fact"],
        "passenger_case": ["Invented contradiction"],
        "next_experiments": ["Validate with an independent perturbation assay."],
    }
    grounded = _ground_generated_narrative(generated, items, fallback)
    assert grounded["driver_case"] == [items[0].title]
    assert "Invented causal fact" not in grounded["driver_case"]
    assert grounded["passenger_case"] == fallback["passenger_case"]
