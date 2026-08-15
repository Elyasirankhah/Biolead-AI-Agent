from pathlib import Path

from app.reference_standard import eval_ready_pairs, load_reference_standard, summarize_reference_standard


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "reference_standard_v1.json"


def test_reference_standard_has_1000_pairs():
    report = load_reference_standard(FIXTURE)
    assert report["n_pairs"] == 1000
    assert len(report["pairs"]) == 1000
    assert report["version"] == "1.1.0"
    assert report.get("scope") == "dermatology_only"


def test_reference_standard_is_dermatology_only():
    report = load_reference_standard(FIXTURE)
    diseases = {str(p["disease"]).lower() for p in report["pairs"]}
    forbidden = {
        "asthma",
        "type 2 diabetes mellitus",
        "coronary artery disease",
        "alzheimer disease",
        "schizophrenia",
        "breast carcinoma",
        "rheumatoid arthritis",
        "inflammatory bowel disease",
    }
    assert not (diseases & forbidden)
    # Must include core dermatology indications.
    joined = " | ".join(diseases)
    assert "atopic" in joined or "eczema" in joined
    assert "psoriasis" in joined


def test_reference_standard_has_high_confidence_eval_slice():
    report = load_reference_standard(FIXTURE)
    ready = eval_ready_pairs(report)
    assert len(ready) >= 50
    assert all(p["label"] in {"driver", "non_driver"} for p in ready)
    assert all(p["confidence"] == "high" for p in ready)
    # Unresolved must exist and must not enter pos/neg eval set.
    unresolved = [p for p in report["pairs"] if p["label"] == "unresolved"]
    assert unresolved
    assert all(p["label"] != "unresolved" for p in ready)


def test_reference_standard_includes_ad_seed_drivers():
    report = load_reference_standard(FIXTURE)
    by_gene = {
        (p["gene"], p["efo_id"]): p
        for p in report["pairs"]
        if p["efo_id"] == "MONDO_0004980"
    }
    for gene in ("IL4R", "IL13", "JAK1"):
        row = by_gene.get((gene, "MONDO_0004980"))
        assert row is not None, gene
        assert row["label"] == "driver"
        assert row["confidence"] == "high"


def test_reference_standard_summary_contract():
    summary = summarize_reference_standard(FIXTURE)
    assert summary["n_pairs"] == 1000
    assert "no universal gold standard" in summary["presentation_statement"].lower()
    assert summary["evaluation_policy"]["exclude_from_pos_neg"] == ["unresolved"]
