import asyncio

from app.feedback import apply_scientist_feedback
from app.feedback_models import FeedbackCreate, FeedbackRecord
from app.feedback_store import clear_memory_feedback, list_feedback, save_feedback
from app.fixtures import get_demo_evidence
from app.models import EvidenceQuality
from app.provenance import apply_provenance_gate
from app.scoring import score_evidence


def test_feedback_irrelevant_removes_from_scoring():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    accepted, _ = apply_provenance_gate(items)
    target = accepted[0]
    fb = FeedbackRecord(
        feedback_id="f1",
        disease="Atopic dermatitis",
        gene="IL4R",
        evidence_id=target.id,
        label="irrelevant",
    )
    kept, removed, summary = apply_scientist_feedback(accepted, [fb])
    assert summary.irrelevant == 1
    assert target.id not in {item.id for item in kept}
    assert target.id in {item.id for item in removed}
    assert removed[0].provenance_reason == "scientist_feedback_irrelevant"


def test_feedback_wrong_direction_and_important():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    accepted, _ = apply_provenance_gate(items)
    inhibit_item = next(item for item in accepted if item.direction == "inhibit")
    moderate = next(
        (item for item in accepted if item.quality == EvidenceQuality.MODERATE),
        accepted[-1],
    )
    fbs = [
        FeedbackRecord(
            feedback_id="f2",
            disease="Atopic dermatitis",
            gene="IL4R",
            evidence_id=inhibit_item.id,
            label="wrong_direction",
        ),
        FeedbackRecord(
            feedback_id="f3",
            disease="Atopic dermatitis",
            gene="IL4R",
            evidence_id=moderate.id,
            label="important",
        ),
    ]
    kept, _, summary = apply_scientist_feedback(accepted, fbs)
    by_id = {item.id: item for item in kept}
    assert summary.wrong_direction == 1
    assert summary.important == 1
    assert by_id[inhibit_item.id].direction == "activate"
    assert by_id[moderate.id].directness >= moderate.directness


def test_feedback_store_memory_roundtrip():
    async def _run():
        clear_memory_feedback()
        await save_feedback(
            FeedbackCreate(
                disease="Atopic dermatitis",
                gene="flg",
                evidence_id="flg-genetics",
                label="important",
            )
        )
        rows = await list_feedback(disease="Atopic dermatitis", gene="FLG")
        assert len(rows) == 1
        assert rows[0].gene == "FLG"
        assert rows[0].label == "important"
        # Latest label wins for same evidence.
        await save_feedback(
            FeedbackCreate(
                disease="Atopic dermatitis",
                gene="FLG",
                evidence_id="flg-genetics",
                label="irrelevant",
            )
        )
        rows2 = await list_feedback(disease="Atopic dermatitis", gene="FLG")
        assert len(rows2) == 1
        assert rows2[0].label == "irrelevant"
        clear_memory_feedback()

    asyncio.run(_run())


def test_feedback_changes_score_when_important_clinical_boosted():
    items = get_demo_evidence("Atopic dermatitis", "S100A8")
    accepted, _ = apply_provenance_gate(items)
    before, _, _ = score_evidence(accepted)
    fb = FeedbackRecord(
        feedback_id="f4",
        disease="Atopic dermatitis",
        gene="S100A8",
        evidence_id=accepted[0].id,
        label="important",
    )
    kept, _, _ = apply_scientist_feedback(accepted, [fb])
    after, _, _ = score_evidence(kept)
    assert after.evidence_quality.value >= before.evidence_quality.value
