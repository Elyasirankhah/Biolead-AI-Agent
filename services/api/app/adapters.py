from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .models import EvidenceItem, EvidenceQuality, EvidenceType

_WS = re.compile(r"\s+")
_DISEASE_STOP = re.compile(r"[^a-z0-9\s]+")


def _norm_text(value: str) -> str:
    return _WS.sub(" ", value.strip().lower())


def _disease_tokens(disease: str) -> set[str]:
    cleaned = _DISEASE_STOP.sub(" ", disease.lower())
    return {token for token in cleaned.split() if len(token) > 2}


def _content_fingerprint(item: EvidenceItem) -> str:
    payload = f"{item.category.value}|{_norm_text(item.title)}|{_norm_text(item.summary[:180])}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _quality_rank(quality: EvidenceQuality) -> int:
    return {EvidenceQuality.HIGH: 3, EvidenceQuality.MODERATE: 2, EvidenceQuality.LOW: 1}[quality]


def normalize_evidence(items: list[EvidenceItem], *, max_items: int = 10) -> list[EvidenceItem]:
    usable: list[EvidenceItem] = []
    for item in items:
        title = item.title.strip()
        summary = item.summary.strip()
        if len(title) < 8 or len(summary) < 24:
            continue
        if "metadata-only" in summary.lower():
            continue
        usable.append(item)

    usable.sort(
        key=lambda item: (
            _quality_rank(item.quality),
            item.directness,
            1 if item.stance == "supports" else 0,
        ),
        reverse=True,
    )

    selected: list[EvidenceItem] = []
    seen_fingerprints: set[str] = set()
    seen_independent: set[str] = set()
    low_genetics_kept = False

    for item in usable:
        fingerprint = _content_fingerprint(item)
        if fingerprint in seen_fingerprints:
            continue
        if item.independent_key in seen_independent:
            continue

        is_low_mapped_genetics = (
            item.category == EvidenceType.HUMAN_GENETICS
            and item.quality == EvidenceQuality.LOW
            and (
                "mapped near" in item.title.lower()
                or "nearest/mapped-gene" in item.summary.lower()
            )
        )
        if is_low_mapped_genetics:
            if low_genetics_kept:
                continue
            low_genetics_kept = True

        selected.append(item)
        seen_fingerprints.add(fingerprint)
        seen_independent.add(item.independent_key)
        if len(selected) >= max_items:
            break

    # Stable display order: causal pillars first, then association/literature.
    priority = {
        EvidenceType.MENDELIAN_RANDOMIZATION: 0,
        EvidenceType.COLOCALIZATION: 1,
        EvidenceType.CLINICAL_PHARMACOLOGY: 2,
        EvidenceType.CAUSAL_PERTURBATION: 3,
        EvidenceType.HUMAN_GENETICS: 4,
        EvidenceType.MECHANISTIC_COHERENCE: 5,
        EvidenceType.DIFFERENTIAL_EXPRESSION: 6,
        EvidenceType.LITERATURE: 7,
    }
    selected.sort(
        key=lambda item: (
            priority.get(item.category, 99),
            -_quality_rank(item.quality),
            -item.directness,
        )
    )
    return selected


class EvidenceAdapter(ABC):
    name: str

    @abstractmethod
    async def collect(self, disease: str, gene: str, tissue: str) -> list[EvidenceItem]:
        raise NotImplementedError


class TTLCache:
    def __init__(self, ttl_hours: int = 24) -> None:
        self.ttl = timedelta(hours=ttl_hours)
        self.values: dict[str, tuple[datetime, Any]] = {}

    def get(self, key: str) -> Any | None:
        cached = self.values.get(key)
        if not cached or datetime.now(timezone.utc) - cached[0] > self.ttl:
            self.values.pop(key, None)
            return None
        return cached[1]

    def set(self, key: str, value: Any) -> None:
        self.values[key] = (datetime.now(timezone.utc), value)


class OpenTargetsAdapter(EvidenceAdapter):
    name = "Open Targets"
    endpoint = "https://api.platform.opentargets.org/api/v4/graphql"

    def __init__(self, client: httpx.AsyncClient, cache: TTLCache) -> None:
        self.client = client
        self.cache = cache

    async def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        key = "ot:" + hashlib.sha256(f"{query}{variables}".encode()).hexdigest()
        if cached := self.cache.get(key):
            return cached
        response = await self.client.post(
            self.endpoint,
            json={"query": query, "variables": variables},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(payload["errors"][0]["message"])
        self.cache.set(key, payload["data"])
        return payload["data"]

    async def _resolve(self, text: str, entity: str) -> str | None:
        query = """
        query Search($queryString: String!, $entityNames: [String!]) {
          search(queryString: $queryString, entityNames: $entityNames, page: {index: 0, size: 5}) {
            hits { id name entity }
          }
        }
        """
        data = await self._graphql(query, {"queryString": text, "entityNames": [entity]})
        hits = data.get("search", {}).get("hits", [])
        exact = next((hit for hit in hits if hit.get("name", "").lower() == text.lower()), None)
        return (exact or (hits[0] if hits else {})).get("id")

    async def collect(self, disease: str, gene: str, tissue: str) -> list[EvidenceItem]:
        target_id = await self._resolve(gene, "target")
        disease_id = await self._resolve(disease, "disease")
        if not target_id or not disease_id:
            return []
        query = """
        query Association($targetId: String!, $diseaseId: String!) {
          disease(efoId: $diseaseId) {
            associatedTargets(
              page: {index: 0, size: 1}
              Bs: [$targetId]
            ) {
              rows {
                target { id approvedSymbol }
                score
                datatypeScores { id score }
              }
            }
          }
        }
        """
        data = await self._graphql(query, {"targetId": target_id, "diseaseId": disease_id})
        rows = (data.get("disease") or {}).get("associatedTargets", {}).get("rows", [])
        if not rows:
            return []
        row = rows[0]
        items: list[EvidenceItem] = []
        labels = {
            "genetic_association": "genetic association",
            "known_drug": "known drug / clinical",
            "affected_pathway": "pathway / mechanism",
            "rna_expression": "RNA expression",
        }
        mapping = {
            "genetic_association": EvidenceType.HUMAN_GENETICS,
            "known_drug": EvidenceType.CLINICAL_PHARMACOLOGY,
            "affected_pathway": EvidenceType.MECHANISTIC_COHERENCE,
            "rna_expression": EvidenceType.DIFFERENTIAL_EXPRESSION,
        }
        for score in row.get("datatypeScores", []):
            category = mapping.get(score["id"])
            if not category or score["score"] <= 0.05:
                continue
            value = float(score["score"])
            label = labels.get(score["id"], score["id"].replace("_", " "))
            items.append(
                EvidenceItem(
                    id=f"ot-{gene.lower()}-{score['id']}",
                    category=category,
                    title=f"Open Targets {label} for {gene}",
                    summary=(
                        f"Open Targets reports a {label} association score of {value:.2f} "
                        f"between {gene} and {disease}. This is target–disease association strength, "
                        f"not a standalone causal proof."
                    ),
                    source_name=self.name,
                    source_url=f"https://platform.opentargets.org/evidence/{target_id}/{disease_id}",
                    quality=EvidenceQuality.HIGH if value >= 0.65 else EvidenceQuality.MODERATE,
                    directness=min(0.95, max(0.35, value)),
                    independent_key=f"ot-{score['id']}",
                    raw_source=f"Open Targets target={target_id}, disease={disease_id}",
                )
            )
        return items


class EuropePMCAdapter(EvidenceAdapter):
    name = "Europe PMC"
    endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, client: httpx.AsyncClient, cache: TTLCache) -> None:
        self.client = client
        self.cache = cache

    async def collect(self, disease: str, gene: str, tissue: str) -> list[EvidenceItem]:
        query = f'TITLE_ABS:"{gene}" AND TITLE_ABS:"{disease}"'
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
        items: list[EvidenceItem] = []
        seen_titles: set[str] = set()
        for result in payload.get("resultList", {}).get("result", []):
            source = result.get("source", "MED")
            identifier = result.get("id") or result.get("pmid")
            if not identifier:
                continue
            title = (result.get("title") or "").strip()
            abstract = (result.get("abstractText") or "").strip()
            if not title or not abstract:
                continue
            title_key = _norm_text(title)
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            items.append(
                EvidenceItem(
                    id=f"epmc-{identifier}",
                    category=EvidenceType.LITERATURE,
                    title=title[:180],
                    summary=(abstract[:300] + "…") if len(abstract) > 300 else abstract,
                    source_name=self.name,
                    source_url=f"https://europepmc.org/article/{source}/{identifier}",
                    citation=f"{source}:{identifier}",
                    quality=EvidenceQuality.MODERATE,
                    directness=0.55,
                    independent_key=f"publication-{identifier}",
                    excerpt=abstract[:500] or None,
                    raw_source="Europe PMC REST API result",
                )
            )
            if len(items) >= 3:
                break
        return items


class GWASCatalogAdapter(EvidenceAdapter):
    name = "GWAS Catalog"
    endpoint = "https://www.ebi.ac.uk/gwas/rest/api/v2/associations"
    GENOME_WIDE_SIG = 5e-8

    def __init__(self, client: httpx.AsyncClient, cache: TTLCache) -> None:
        self.client = client
        self.cache = cache

    @staticmethod
    def _efo_trait(association: dict[str, Any]) -> tuple[str, str | None]:
        efo = association.get("efo_traits") or []
        if isinstance(efo, list) and efo:
            first = efo[0]
            if isinstance(first, dict):
                return (
                    (first.get("efo_trait") or "").strip(),
                    (first.get("efo_id") or None),
                )
        reported = association.get("reported_trait") or []
        if isinstance(reported, list) and reported and isinstance(reported[0], str):
            return reported[0].strip(), None
        return "", None

    @staticmethod
    def _pvalue(association: dict[str, Any]) -> float | None:
        raw = association.get("p_value")
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
        mantissa = association.get("pvalue_mantissa")
        exponent = association.get("pvalue_exponent")
        if isinstance(mantissa, (int, float)) and isinstance(exponent, (int, float)):
            return float(mantissa) * (10 ** float(exponent))
        return None

    @staticmethod
    def _p_text(association: dict[str, Any], pvalue: float | None) -> str:
        mantissa = association.get("pvalue_mantissa")
        exponent = association.get("pvalue_exponent")
        if isinstance(mantissa, (int, float)) and isinstance(exponent, (int, float)):
            return f"{int(mantissa)}×10^{int(exponent)}"
        if isinstance(pvalue, float):
            return f"{pvalue:.1e}"
        return "n/a"

    @staticmethod
    def _rs_id(association: dict[str, Any]) -> str | None:
        alleles = association.get("snp_allele") or []
        if isinstance(alleles, list) and alleles and isinstance(alleles[0], dict):
            rs = alleles[0].get("rs_id")
            if isinstance(rs, str) and rs.strip():
                return rs.strip()
        # Fallback: parse from _links.snp.href
        snp_link = ((association.get("_links") or {}).get("snp") or {}).get("href", "")
        if isinstance(snp_link, str):
            match = re.search(r"(rs\d+)", snp_link)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _effect_size(association: dict[str, Any]) -> str | None:
        or_val = association.get("or_per_copy_num") or association.get("or_value")
        try:
            or_val = float(or_val) if or_val not in (None, "-", "") else None
        except (TypeError, ValueError):
            or_val = None
        beta = association.get("beta")
        try:
            beta = float(beta) if beta not in (None, "-", "") else None
        except (TypeError, ValueError):
            beta = None
        ci_lower = association.get("ci_lower")
        ci_upper = association.get("ci_upper")
        if or_val is not None:
            if isinstance(ci_lower, (int, float)) and isinstance(ci_upper, (int, float)):
                return f"OR={or_val:.2f} (95% CI {ci_lower:.2f}–{ci_upper:.2f})"
            return f"OR={or_val:.2f}"
        if beta is not None:
            return f"β={beta:.2f}"
        return None

    async def collect(self, disease: str, gene: str, tissue: str) -> list[EvidenceItem]:
        key = f"gwas:{gene}:{disease}"
        payload = self.cache.get(key)
        if payload is None:
            response = await self.client.get(
                self.endpoint,
                params={"mapped_gene": gene, "size": 15, "extended_geneset": "false"},
                headers={"Accept": "application/json"},
                timeout=25,
            )
            response.raise_for_status()
            payload = response.json()
            self.cache.set(key, payload)

        associations = payload.get("_embedded", {}).get("associations", [])
        if not associations:
            return []

        disease_tokens = _disease_tokens(disease)

        def _overlap(trait: str) -> int:
            trait_tokens = set(re.split(r"\W+", trait.lower())) - {""}
            return len(disease_tokens & trait_tokens)

        ranked: list[tuple[int, float, dict[str, Any], str, str | None]] = []
        for association in associations:
            trait, efo_id = self._efo_trait(association)
            if not trait:
                continue
            overlap = _overlap(trait)
            pvalue = self._pvalue(association)
            # Rank: disease-matching traits first, then more significant (smaller) pvalue.
            log_p = 0.0
            if pvalue is not None and pvalue > 0:
                log_p = -math.log10(pvalue)
            ranked.append((overlap, log_p, association, trait, efo_id))

        if not ranked:
            return []

        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        best_overlap, best_log_p, association, trait, efo_id = ranked[0]
        pvalue = self._pvalue(association)

        # Value gate — no more empty "mapped near" noise.
        if best_overlap == 0 and (pvalue is None or pvalue >= self.GENOME_WIDE_SIG):
            return []

        rs_id = self._rs_id(association)
        accession = association.get("accession_id") or association.get("accessionId")
        pubmed_id = association.get("pubmed_id")
        first_author = association.get("first_author")
        effect = self._effect_size(association)
        locations = association.get("locations") or []
        location_text = locations[0] if isinstance(locations, list) and locations else None
        p_text = self._p_text(association, pvalue)

        if rs_id:
            source_url = f"https://www.ebi.ac.uk/gwas/variants/{rs_id}"
        elif accession:
            source_url = f"https://www.ebi.ac.uk/gwas/studies/{accession}"
        else:
            source_url = f"https://www.ebi.ac.uk/gwas/search?query={gene}"

        variant = rs_id or "mapped variant"
        matched = best_overlap > 0
        quality = EvidenceQuality.MODERATE if matched else EvidenceQuality.LOW
        directness = 0.5 if matched else 0.35

        title = f"GWAS Catalog: {variant} near {gene} — {trait} (p={p_text})"

        summary_parts = [
            (
                f"Genome-wide association study reports {variant} mapped to {gene}"
                + (f" at {location_text}" if location_text else "")
                + f" for {trait} (p={p_text}"
                + (f"; {effect}" if effect else "")
                + ")."
            )
        ]
        if first_author and pubmed_id:
            summary_parts.append(f"Source: {first_author} et al., PMID {pubmed_id}.")
        if matched:
            summary_parts.append(
                "Trait matches the query disease — this is real human-genetics support, "
                f"but nearest/mapped-gene assignment is *not* proof that {gene} is the causal "
                "gene at this locus (fine-mapping / colocalization needed)."
            )
        else:
            summary_parts.append(
                f"Trait '{trait}' is not the query disease; kept because the association is "
                "at/near genome-wide significance and is still context worth acknowledging."
            )

        return [
            EvidenceItem(
                id=f"gwas-{accession or association.get('association_id') or 'unknown'}",
                category=EvidenceType.HUMAN_GENETICS,
                title=title[:220],
                summary=" ".join(summary_parts),
                source_name=self.name,
                source_url=source_url,
                citation=f"PMID:{pubmed_id}" if pubmed_id else None,
                quality=quality,
                directness=directness,
                independent_key=f"gwas-{rs_id or accession or gene.lower()}",
                excerpt=(
                    f"{variant} · {trait}"
                    + (f" · {effect}" if effect else "")
                    + f" · p={p_text}"
                ),
                raw_source=(
                    f"GWAS Catalog association_id={association.get('association_id')} "
                    f"accession={accession} efo={efo_id}"
                ),
            )
        ]


async def collect_live_evidence(disease: str, gene: str, tissue: str) -> tuple[list[EvidenceItem], list[str]]:
    cache = TTLCache()
    errors: list[str] = []
    items: list[EvidenceItem] = []
    async with httpx.AsyncClient(headers={"User-Agent": "BioLead/1.0 research prototype"}) as client:
        adapters: list[EvidenceAdapter] = [
            OpenTargetsAdapter(client, cache),
            EuropePMCAdapter(client, cache),
            GWASCatalogAdapter(client, cache),
        ]
        for adapter in adapters:
            try:
                items.extend(await adapter.collect(disease, gene, tissue))
            except Exception as exc:  # External sources should degrade independently.
                errors.append(f"{adapter.name}: {type(exc).__name__}")
    return normalize_evidence(items), errors
