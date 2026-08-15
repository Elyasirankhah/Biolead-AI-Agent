from app.models import EvidenceItem, EvidenceQuality, EvidenceType
from app.provenance import apply_provenance_gate, verify_evidence_item
from app.fixtures import get_demo_evidence
from app.scoring import score_evidence


def _item(**overrides) -> EvidenceItem:
    base = dict(
        id="ev-1",
        category=EvidenceType.LITERATURE,
        title="A solid enough evidence title",
        summary="This summary is long enough to pass the structural provenance checks for BioLead.",
        source_name="PubMed",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        quality=EvidenceQuality.MODERATE,
        independent_key="ev-1-key",
        citation="PMID:12345678",
    )
    base.update(overrides)
    return EvidenceItem(**base)


def test_provenance_accepts_trusted_source():
    item = verify_evidence_item(_item())
    assert item.provenance_status == "accepted"


def test_provenance_rejects_placeholder_host():
    item = verify_evidence_item(_item(source_url="https://example.com/fake", citation=None))
    assert item.provenance_status == "rejected"
    assert "placeholder" in (item.provenance_reason or "")


def test_provenance_rejects_unallowlisted_host_without_pmid():
    item = verify_evidence_item(
        _item(
            source_url="https://my-random-site.io/paper/123",
            citation=None,
            source_name="Blog",
        )
    )
    assert item.provenance_status == "rejected"
    assert "allowlist" in (item.provenance_reason or "")


def test_rejected_evidence_does_not_drive_score():
    good = get_demo_evidence("Atopic dermatitis", "IL4R")
    bad = _item(
        id="fake-driver",
        category=EvidenceType.CLINICAL_PHARMACOLOGY,
        title="Invented clinical rescue claim for scoring inflation",
        summary="This would wrongly boost actionability if provenance were ignored by the scorer.",
        source_url="https://example.com/not-real",
        citation=None,
        quality=EvidenceQuality.HIGH,
        directness=0.95,
        independent_key="fake-clinical",
    )
    accepted, rejected = apply_provenance_gate([*good, bad])
    assert bad.id in {item.id for item in rejected}
    assert bad.id not in {item.id for item in accepted}
    score_with_gate, _, _ = score_evidence(accepted)
    score_if_cheated, _, _ = score_evidence([*accepted, bad.model_copy(update={"provenance_status": "accepted"})])
    assert score_with_gate.actionability.value <= score_if_cheated.actionability.value
