import asyncio

from app.fixtures import get_demo_evidence
from app.ledger import build_decision_ledger
from app.provenance import apply_provenance_gate
from app.reasoning import build_result
from app.scoring import score_evidence
from app.snapshot import build_decision_snapshot


def test_snapshot_hash_stable_for_identical_evidence():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    accepted, _ = apply_provenance_gate(items)
    scorecard, verdict, _ = score_evidence(accepted)
    a = build_decision_snapshot(
        gene="IL4R",
        disease="Atopic dermatitis",
        tissue="skin",
        direction="inhibit",
        verdict=verdict,
        accepted_items=accepted,
        mode="demo",
    )
    b = build_decision_snapshot(
        gene="IL4R",
        disease="Atopic dermatitis",
        tissue="skin",
        direction="inhibit",
        verdict=verdict,
        accepted_items=list(reversed(accepted)),
        mode="demo",
    )
    assert a["content_hash"] == b["content_hash"]
    assert a["snapshot_id"] == b["snapshot_id"]
    assert a["rules_version"] == b["rules_version"]
    assert scorecard.scoring_version in a["rules_version"]


def test_ledger_snapshot_matches_builder():
    items = get_demo_evidence("Atopic dermatitis", "FLG")
    accepted, rejected = apply_provenance_gate(items)
    scorecard, verdict, _ = score_evidence(accepted)
    ledger = build_decision_ledger(
        gene="FLG",
        disease="Atopic dermatitis",
        tissue="skin",
        verdict=verdict,
        direction="activate",
        items=accepted,
        scorecard=scorecard,
        rejected_items=rejected,
        mode="demo",
    )
    snap = build_decision_snapshot(
        gene="FLG",
        disease="Atopic dermatitis",
        tissue="skin",
        direction="activate",
        verdict=verdict,
        accepted_items=accepted,
        mode="demo",
    )
    assert ledger.snapshot_id == snap["snapshot_id"]
    assert ledger.content_hash == snap["content_hash"]
    assert ledger.reproducible is True


def test_repeated_build_result_same_snapshot():
    async def _run():
        items = get_demo_evidence("Atopic dermatitis", "S100A8")
        first = await build_result(
            "Atopic dermatitis",
            "S100A8",
            "skin",
            items,
            provider=None,
            mode="demo",
        )
        second = await build_result(
            "Atopic dermatitis",
            "S100A8",
            "skin",
            items,
            provider=None,
            mode="demo",
        )
        assert first.verdict == second.verdict
        assert first.decision_ledger is not None
        assert second.decision_ledger is not None
        assert first.decision_ledger.content_hash == second.decision_ledger.content_hash
        assert first.decision_ledger.snapshot_id == second.decision_ledger.snapshot_id
        # run_id can differ; snapshot must not.
        assert first.run_id != "" and second.run_id != ""

    asyncio.run(_run())
