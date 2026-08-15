from app.falsification import classify_pair, run_falsification
from app.fixtures import get_demo_evidence
from app.models import EvidenceItem, EvidenceQuality, EvidenceType
from app.provenance import apply_provenance_gate


def test_falsification_gate_completes_for_demo_genes():
    for gene in ("IL4R", "FLG", "S100A8"):
        items = get_demo_evidence("Atopic dermatitis", gene)
        accepted, _ = apply_provenance_gate(items)
        result = run_falsification(
            gene=gene,
            disease="Atopic dermatitis",
            direction="inhibit" if gene == "IL4R" else "activate" if gene == "FLG" else "unresolved",
            items=accepted,
        )
        assert result.gate.gate_completed is True
        assert result.gate.status in {"PASSED", "UNRESOLVED"}
        assert result.gate.counter_hypotheses
        assert result.gate.counter_queries
        assert result.gate.hypothesis_tested


def test_il4r_falsification_passes_without_hard_block():
    items = get_demo_evidence("Atopic dermatitis", "IL4R")
    accepted, _ = apply_provenance_gate(items)
    result = run_falsification(
        gene="IL4R",
        disease="Atopic dermatitis",
        direction="inhibit",
        items=accepted,
    )
    assert result.gate.status == "PASSED"
    assert result.blocks_driver is False


def test_hard_vs_contextual_classification():
    human = EvidenceItem(
        id="a",
        category=EvidenceType.CLINICAL_PHARMACOLOGY,
        title="Human pharmacological inhibition improves disease in randomized trial",
        summary="A randomized human clinical trial showed pharmacological inhibition improved atopic dermatitis.",
        source_name="PubMed",
        source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        quality=EvidenceQuality.HIGH,
        stance="supports",
        direction="inhibit",
        independent_key="a",
        provenance_status="accepted",
    )
    mouse = EvidenceItem(
        id="b",
        category=EvidenceType.CAUSAL_PERTURBATION,
        title="Embryonic mouse knockout worsens developmental phenotype",
        summary="Complete embryonic mouse knockout worsened a developmental phenotype unrelated to adult pharmacology.",
        source_name="PubMed",
        source_url="https://pubmed.ncbi.nlm.nih.gov/2/",
        quality=EvidenceQuality.HIGH,
        stance="contradicts",
        direction="activate",
        independent_key="b",
        provenance_status="accepted",
    )
    contextual = classify_pair(human, mouse)
    assert contextual.classification == "contextual"

    oppose = EvidenceItem(
        id="c",
        category=EvidenceType.HUMAN_GENETICS,
        title="Human genetics shows opposite causal direction for the same disease",
        summary="Human genetic evidence indicates activation, not inhibition, is protective in patients.",
        source_name="Open Targets",
        source_url="https://platform.opentargets.org/target/ENSG00000077238",
        quality=EvidenceQuality.HIGH,
        stance="contradicts",
        direction="activate",
        independent_key="c",
        provenance_status="accepted",
    )
    hard = classify_pair(human, oppose)
    assert hard.classification == "hard"
