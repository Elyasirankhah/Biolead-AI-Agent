from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import httpx

from .adapters import (
    EuropePMCAdapter,
    EvidenceAdapter,
    GWASCatalogAdapter,
    OpenTargetsAdapter,
    normalize_evidence,
)
from .cache import EvidenceCache, get_evidence_cache
from .falsification import counter_search_queries
from .models import EvidenceItem, EvidenceQuality, EvidenceType

_TOKEN = re.compile(r"[a-z0-9]+")
_CAUSAL_BOOST = {
    "trial",
    "randomized",
    "genetic",
    "gwas",
    "causal",
    "knockout",
    "crispr",
    "inhibition",
    "inhibitor",
    "antibody",
    "efficacy",
    "colocali",
    "mendelian",
    "perturb",
    "rescue",
}
_ASSOC_PENALTY = {"correlation", "correlated", "upregulated", "biomarker", "expression"}


@dataclass
class RagTrace:
    queries: list[str] = field(default_factory=list)
    sources_hit: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    cache_mode: str = "shared"  # shared | fresh
    refreshed: bool = False
    literature_kept: int = 0
    structured_kept: int = 0


@dataclass
class RagResult:
    items: list[EvidenceItem]
    errors: list[str]
    trace: RagTrace


def _tokens(text: str) -> set[str]:
    return {tok for tok in _TOKEN.findall(text.lower()) if len(tok) > 2}


def _literature_relevance(item: EvidenceItem, gene: str, disease: str) -> float:
    blob = f"{item.title} {item.summary} {item.excerpt or ''}".lower()
    toks = _tokens(blob)
    gene_tok = gene.lower()
    disease_toks = _tokens(disease)
    score = 0.0
    if gene_tok in blob:
        score += 2.0
    score += 1.2 * len(disease_toks & toks)
    score += 0.8 * sum(1 for term in _CAUSAL_BOOST if term in blob)
    score -= 0.5 * sum(1 for term in _ASSOC_PENALTY if term in blob)
    # Prefer items with PMID-like citations.
    if item.citation and "pmid" in item.citation.lower():
        score += 0.4
    if item.quality == EvidenceQuality.HIGH:
        score += 0.3
    return score


def _rerank_literature(items: list[EvidenceItem], gene: str, disease: str, *, keep: int = 5) -> list[EvidenceItem]:
    lit = [item for item in items if item.category == EvidenceType.LITERATURE]
    other = [item for item in items if item.category != EvidenceType.LITERATURE]
    ranked = sorted(lit, key=lambda item: _literature_relevance(item, gene, disease), reverse=True)
    return other + ranked[:keep]


class MultiQueryEuropePMC(EuropePMCAdapter):
    """Europe PMC with support + falsification query fan-out."""

    async def collect(self, disease: str, gene: str, tissue: str) -> list[EvidenceItem]:
        support_q = f'TITLE_ABS:"{gene}" AND TITLE_ABS:"{disease}"'
        falsify_q = (
            f'TITLE_ABS:"{gene}" AND TITLE_ABS:"{disease}" AND '
            f'(worsens OR contradictory OR "not associated" OR passenger OR biomarker OR adverse)'
        )
        queries = [support_q, falsify_q]
        # Keep one extra biology-context query when tissue is provided.
        if tissue and tissue.lower() not in {"unknown", "n/a"}:
            queries.append(f'TITLE_ABS:"{gene}" AND TITLE_ABS:"{disease}" AND TITLE_ABS:"{tissue}"')

        merged: list[EvidenceItem] = []
        seen: set[str] = set()
        for query in queries:
            key = f"epmc:{query}"
            payload = self.cache.get(key)
            if payload is None:
                response = await self.client.get(
                    self.endpoint,
                    params={
                        "query": query,
                        "format": "json",
                        "pageSize": 8,
                        "resultType": "core",
                        "sort": "CITED desc",
                    },
                    timeout=25,
                )
                response.raise_for_status()
                payload = response.json()
                self.cache.set(key, payload)
            for result in payload.get("resultList", {}).get("result", []):
                source = result.get("source", "MED")
                identifier = result.get("id") or result.get("pmid")
                if not identifier:
                    continue
                title = (result.get("title") or "").strip()
                abstract = (result.get("abstractText") or "").strip()
                if not title or not abstract:
                    continue
                title_key = title.strip().lower()
                if title_key in seen:
                    continue
                seen.add(title_key)
                stance = "supports"
                low = f"{title} {abstract}".lower()
                if any(tok in low for tok in ("worsen", "not associated", "no association", "contradict", "adverse")):
                    stance = "contradicts"
                elif any(tok in low for tok in ("biomarker", "correlat", "upregulated", "passenger")):
                    # Association-leaning literature stays supports but weaker.
                    stance = "supports"
                merged.append(
                    EvidenceItem(
                        id=f"epmc-{identifier}",
                        category=EvidenceType.LITERATURE,
                        title=title[:180],
                        summary=(abstract[:300] + "…") if len(abstract) > 300 else abstract,
                        source_name=self.name,
                        source_url=f"https://europepmc.org/article/{source}/{identifier}",
                        citation=f"{source}:{identifier}",
                        quality=EvidenceQuality.MODERATE,
                        stance=stance,  # type: ignore[arg-type]
                        directness=0.55 if stance == "supports" else 0.5,
                        independent_key=f"publication-{identifier}",
                        excerpt=abstract[:500] or None,
                        raw_source=f"Europe PMC RAG query={query[:120]}",
                    )
                )
        return merged[:8]


async def retrieve_rag(
    disease: str,
    gene: str,
    tissue: str,
    *,
    refresh: bool = False,
) -> RagResult:
    """
    Hybrid RAG retrieve:
    - structured sources (Open Targets, GWAS)
    - multi-query literature (Europe PMC)
    - lexical rerank of literature
    - optional cache bypass via refresh=True
    """
    cache = EvidenceCache() if refresh else get_evidence_cache()
    cache_mode = "fresh" if refresh else "shared"
    errors: list[str] = []
    items: list[EvidenceItem] = []
    sources_hit: list[str] = []
    sources_failed: list[str] = []
    queries = [
        f'TITLE_ABS:"{gene}" AND TITLE_ABS:"{disease}"',
        *counter_search_queries(gene, disease, "unresolved")[:3],
    ]

    adapters: list[EvidenceAdapter]
    async with httpx.AsyncClient(headers={"User-Agent": "BioLead/1.1 research prototype"}) as client:
        adapters = [
            OpenTargetsAdapter(client, cache),
            MultiQueryEuropePMC(client, cache),
            GWASCatalogAdapter(client, cache),
        ]
        for adapter in adapters:
            try:
                got = await adapter.collect(disease, gene, tissue)
                if got:
                    sources_hit.append(adapter.name)
                    items.extend(got)
                else:
                    sources_hit.append(f"{adapter.name} (empty)")
            except Exception as exc:  # External sources degrade independently.
                sources_failed.append(adapter.name)
                errors.append(f"{adapter.name}: {type(exc).__name__}")

    reranked = _rerank_literature(items, gene, disease, keep=int(os.getenv("RAG_LIT_KEEP", "5")))
    normalized = normalize_evidence(reranked, max_items=12)
    lit_kept = sum(1 for item in normalized if item.category == EvidenceType.LITERATURE)
    structured_kept = len(normalized) - lit_kept
    trace = RagTrace(
        queries=queries,
        sources_hit=sources_hit,
        sources_failed=sources_failed,
        cache_mode=cache_mode,
        refreshed=refresh,
        literature_kept=lit_kept,
        structured_kept=structured_kept,
    )
    return RagResult(items=normalized, errors=errors, trace=trace)
