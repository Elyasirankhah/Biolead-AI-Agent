from app.ensemble import adjust_confidence, merge_ensemble_votes
from app.fixtures import get_demo_evidence
from app.models import DimensionScore, ScoreCard
from app.reasoning import _ground_vote_trace
from app.scoring import score_evidence


def _card(pillars: int, causality: int) -> ScoreCard:
    return ScoreCard(
        causality=DimensionScore(value=causality, rationale="t"),
        actionability=DimensionScore(value=50, rationale="t"),
        evidence_quality=DimensionScore(value=80, rationale="t"),
        contradiction_penalty=0,
        independent_pillars=pillars,
        evidence_count=3,
    )


def test_deterministic_only_keeps_verdict_when_ensemble_not_required():
    final, trace = merge_ensemble_votes(
        "Driver", None, None, _card(3, 90), require_llm_voters=False
    )
    assert final == "Driver"
    assert trace["policy"] == "deterministic_only"


def test_required_ensemble_abstains_without_voters():
    final, trace = merge_ensemble_votes("Driver", None, None, _card(3, 90))
    assert final == "Insufficient evidence"
    assert trace["policy"] == "ensemble_required_voters_unavailable"


def test_unanimous_ensemble():
    final, trace = merge_ensemble_votes("Passenger", "Passenger", "Passenger", _card(0, 10))
    assert final == "Passenger"
    assert trace["agreement"] is True


def test_disagreement_abstains():
    final, trace = merge_ensemble_votes("Driver", "Passenger", "Insufficient evidence", _card(3, 80))
    assert final == "Insufficient evidence"
    assert trace["policy"] == "disagreement_abstain"


def test_majority_driver_blocked_without_pillars():
    final, trace = merge_ensemble_votes(
        "Insufficient evidence", "Driver", "Driver", _card(1, 40)
    )
    assert final == "Insufficient evidence"
    assert trace["policy"] == "majority_driver_blocked_scientific_threshold"


def test_strong_driver_not_silently_flipped_to_passenger():
    final, trace = merge_ensemble_votes("Driver", "Passenger", "Passenger", _card(3, 90))
    assert final == "Insufficient evidence"
    assert "abstain" in trace["policy"]


def test_confidence_drops_on_disagreement():
    assert adjust_confidence(80, "Insufficient evidence", {"policy": "disagreement_abstain"}) <= 58


def test_vote_trace_removes_unknown_evidence_and_unsupported_pillars():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    scorecard, _, _ = score_evidence(items)
    one_item = items[0]
    trace = _ground_vote_trace(
        {
            "vote": "Driver",
            "causal_pillars": [one_item.category.value, "causal_perturbation"],
            "supporting_evidence_ids": [one_item.id, "invented-evidence"],
            "contradicting_evidence_ids": [],
            "missing_requirements": [],
            "alternative_explanation": "None supported.",
            "rationale": "Claims two pillars despite one cited item.",
            "confidence": 0.95,
        },
        "advocate",
        items,
        scorecard,
    )
    assert trace is not None
    assert trace.vote == "Insufficient evidence"
    assert trace.supporting_evidence_ids == [one_item.id]
    assert trace.causal_pillars == [one_item.category.value]
    assert trace.confidence <= 0.69
    assert "driver_downgraded_scientific_threshold" in trace.guardrail_actions


def test_passenger_vote_requires_grounded_association_and_counterevidence():
    items = get_demo_evidence("Atopic dermatitis", "S100A8")
    scorecard, _, _ = score_evidence(items)
    support = next(item for item in items if item.stance == "supports")
    counter = next(item for item in items if item.stance == "contradicts")
    trace = _ground_vote_trace(
        {
            "vote": "Passenger",
            "causal_pillars": [],
            "supporting_evidence_ids": [support.id],
            "contradicting_evidence_ids": [counter.id],
            "missing_requirements": ["Direct human phenotype rescue"],
            "alternative_explanation": "Inflammatory-state biomarker.",
            "rationale": "Association is present but causal rescue is contradicted.",
            "confidence": 0.82,
        },
        "falsifier",
        items,
        scorecard,
    )
    assert trace is not None
    assert trace.vote == "Passenger"
    assert trace.supporting_evidence_ids == [support.id]
    assert trace.contradicting_evidence_ids == [counter.id]


def test_combined_pillar_string_is_normalized_and_grounded():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    scorecard, _, _ = score_evidence(items)
    causal_items = [
        item
        for item in items
        if item.category.value
        in {"human_genetics", "causal_perturbation", "clinical_pharmacology"}
    ]
    trace = _ground_vote_trace(
        {
            "vote": "Driver",
            "causal_pillars": [
                "human_genetics|causal_perturbation|clinical_pharmacology"
            ],
            "supporting_evidence_ids": [item.id for item in causal_items],
            "contradicting_evidence_ids": [],
            "missing_requirements": [],
            "alternative_explanation": "Pathway-level assignment.",
            "rationale": "Three independently supported causal pillars converge.",
            "confidence": 0.9,
        },
        "advocate",
        items,
        scorecard,
    )
    assert trace is not None
    assert trace.vote == "Driver"
    assert trace.causal_pillars == [
        "human_genetics",
        "causal_perturbation",
        "clinical_pharmacology",
    ]
    assert "causal_pillars_normalized" in trace.guardrail_actions
