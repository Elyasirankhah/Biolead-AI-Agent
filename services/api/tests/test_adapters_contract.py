import asyncio
from types import SimpleNamespace

from app.adapters import GWASCatalogAdapter, TTLCache, normalize_evidence
from app.models import EvidenceItem, EvidenceQuality, EvidenceType


def test_ttl_cache_roundtrip():
    cache = TTLCache(ttl_hours=1)
    cache.set("k", {"ok": True})
    assert cache.get("k") == {"ok": True}


def test_evidence_item_contract_fields():
    item = EvidenceItem(
        id="contract-1",
        category=EvidenceType.LITERATURE,
        title="Contract title",
        summary="Normalized evidence must remain source-linked.",
        source_name="Europe PMC",
        source_url="https://europepmc.org/article/MED/1",
        quality=EvidenceQuality.MODERATE,
        independent_key="publication-1",
        citation="MED:1",
        stance="supports",
        directness=0.55,
    )
    dumped = item.model_dump(mode="json")
    assert dumped["category"] == "literature"
    assert dumped["source_url"].startswith("https://")
    assert dumped["independent_key"]


def _gwas_card(index: int) -> EvidenceItem:
    return EvidenceItem(
        id=f"gwas-{index}",
        category=EvidenceType.HUMAN_GENETICS,
        title="GWAS locus mapped near S100A8",
        summary=(
            "A catalog association maps to this gene. Nearest/mapped-gene evidence is "
            "supporting context, not proof of causal assignment."
        ),
        source_name="GWAS Catalog",
        source_url="https://www.ebi.ac.uk/gwas/",
        quality=EvidenceQuality.LOW,
        directness=0.35,
        independent_key=f"gwas-{index}",
    )


def test_normalize_collapses_duplicate_gwas_cards():
    items = [_gwas_card(1), _gwas_card(2), _gwas_card(3)]
    filtered = normalize_evidence(items)
    assert len(filtered) == 1
    assert filtered[0].category == EvidenceType.HUMAN_GENETICS


def test_normalize_drops_empty_and_metadata_only():
    junk = EvidenceItem(
        id="junk",
        category=EvidenceType.LITERATURE,
        title="Short",
        summary="Metadata-only literature result.",
        source_name="Europe PMC",
        source_url="https://europepmc.org/article/MED/1",
        quality=EvidenceQuality.LOW,
        independent_key="junk",
        directness=0.2,
    )
    good = EvidenceItem(
        id="good",
        category=EvidenceType.LITERATURE,
        title="Useful abstract-backed paper about atopic dermatitis",
        summary="A real abstract describing disease biology and experimental findings in skin.",
        source_name="Europe PMC",
        source_url="https://europepmc.org/article/MED/2",
        quality=EvidenceQuality.MODERATE,
        independent_key="good",
        directness=0.55,
    )
    filtered = normalize_evidence([junk, good])
    assert [item.id for item in filtered] == ["good"]


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def get(self, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse(self._payload)


def _gwas_payload(**overrides) -> dict:
    association = {
        "association_id": 42,
        "accession_id": "GCST0001",
        "p_value": 3e-18,
        "pvalue_mantissa": 3,
        "pvalue_exponent": -18,
        "or_per_copy_num": 1.42,
        "ci_lower": 1.28,
        "ci_upper": 1.58,
        "beta": "-",
        "efo_traits": [{"efo_id": "EFO_0000270", "efo_trait": "atopic dermatitis"}],
        "reported_trait": ["Atopic dermatitis"],
        "snp_allele": [{"rs_id": "rs123456", "effect_allele": "A"}],
        "mapped_genes": ["FLG"],
        "locations": ["1:152300000"],
        "pubmed_id": "12345678",
        "first_author": "Doe J",
        "_links": {
            "self": {"href": "https://x/api/42"},
            "snp": {"href": "https://x/api/snps/rs123456"},
        },
    }
    association.update(overrides)
    return {"_embedded": {"associations": [association]}}


def test_gwas_adapter_parses_v2_schema_disease_match():
    adapter = GWASCatalogAdapter(_FakeClient(_gwas_payload()), TTLCache())
    items = asyncio.run(adapter.collect("atopic dermatitis", "FLG", "skin"))
    assert len(items) == 1
    card = items[0]
    assert "rs123456" in card.title
    assert "atopic dermatitis" in card.title.lower()
    assert str(card.source_url) == "https://www.ebi.ac.uk/gwas/variants/rs123456"
    assert "OR=1.42" in card.summary
    assert card.quality == EvidenceQuality.MODERATE
    assert card.citation == "PMID:12345678"


def test_gwas_adapter_drops_unrelated_weak_hit():
    payload = _gwas_payload(
        p_value=1e-4,
        pvalue_mantissa=1,
        pvalue_exponent=-4,
        efo_traits=[{"efo_id": "EFO_XXX", "efo_trait": "monocyte count"}],
    )
    adapter = GWASCatalogAdapter(_FakeClient(payload), TTLCache())
    items = asyncio.run(adapter.collect("atopic dermatitis", "FLG", "skin"))
    assert items == []


def test_gwas_adapter_keeps_gws_offtrait():
    payload = _gwas_payload(
        p_value=2e-9,
        pvalue_mantissa=2,
        pvalue_exponent=-9,
        efo_traits=[{"efo_id": "EFO_XXX", "efo_trait": "monocyte count"}],
    )
    adapter = GWASCatalogAdapter(_FakeClient(payload), TTLCache())
    items = asyncio.run(adapter.collect("atopic dermatitis", "FLG", "skin"))
    assert len(items) == 1
    card = items[0]
    assert card.quality == EvidenceQuality.LOW
    assert "not the query disease" in card.summary


# Keep SimpleNamespace import used (silences unused-import in some linters).
_ = SimpleNamespace
