from app.models import EvidenceItem, EvidenceQuality, EvidenceType
from app.rag import _literature_relevance, _rerank_literature


def _lit(id_: str, title: str, summary: str, **kwargs) -> EvidenceItem:
    return EvidenceItem(
        id=id_,
        category=EvidenceType.LITERATURE,
        title=title,
        summary=summary,
        source_name="Europe PMC",
        source_url=f"https://europepmc.org/article/MED/{id_}",
        citation=f"PMID:{id_}",
        quality=EvidenceQuality.MODERATE,
        independent_key=f"publication-{id_}",
        **kwargs,
    )


def test_literature_rerank_prefers_causal_language():
    weak = _lit(
        "1",
        "S100A8 expression is upregulated in inflamed skin",
        "Correlation and biomarker observations in atopic dermatitis lesions.",
    )
    strong = _lit(
        "2",
        "Randomized trial of IL4R inhibition in atopic dermatitis",
        "A randomized clinical trial showed efficacy of pharmacological inhibition.",
    )
    ranked = _rerank_literature([weak, strong], "IL4R", "Atopic dermatitis", keep=2)
    assert ranked[0].id == "2"
    assert _literature_relevance(strong, "IL4R", "Atopic dermatitis") > _literature_relevance(
        weak, "IL4R", "Atopic dermatitis"
    )


def test_rerank_keeps_structured_ahead_of_trimmed_literature():
    structured = EvidenceItem(
        id="ot-1",
        category=EvidenceType.CLINICAL_PHARMACOLOGY,
        title="Open Targets known drug evidence for IL4R",
        summary="Open Targets reports known drug association between IL4R and atopic dermatitis.",
        source_name="Open Targets",
        source_url="https://platform.opentargets.org/evidence/ENSG1/EFO1",
        quality=EvidenceQuality.HIGH,
        independent_key="ot-known_drug",
    )
    papers = [
        _lit(str(i), f"Paper {i} about IL4R atopic dermatitis expression", "Expression association only." * 2)
        for i in range(10, 16)
    ]
    ranked = _rerank_literature([*papers, structured], "IL4R", "Atopic dermatitis", keep=3)
    assert ranked[0].id == "ot-1"
    assert sum(1 for item in ranked if item.category == EvidenceType.LITERATURE) == 3
