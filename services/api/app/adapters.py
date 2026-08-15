from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .cache import EvidenceCache, get_evidence_cache
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
    """
    Keep evidence interview-ready:
    - drop empty / placeholder cards
    - collapse near-duplicate titles+summaries
    - keep at most one LOW nearest-gene genetics hit
    - prefer higher quality / directness
    """
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


# Backward-compatible alias used by tests.
TTLCache = EvidenceCache


class OpenTargetsAdapter(EvidenceAdapter):
    name = "Open Targets"
    endpoint = "https://api.platform.opentargets.org/api/v4/graphql"

    def __init__(self, client: httpx.AsyncClient, cache: EvidenceCache) -> None:
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
        raw = (text or "").strip()
        if not raw:
            return None
        # Allow exact ontology IDs from the reference standard.
        if entity == "disease" and (
            raw.startswith("MONDO_")
            or raw.startswith("EFO_")
            or raw.startswith("HP_")
            or raw.startswith("Orphanet_")
        ):
            return raw
        if entity == "target" and raw.startswith("ENSG"):
            return raw
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
        # Prefer ontology ID when callers provide it (reference-standard eval).
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
                datasourceScores { id score }
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
        return self._project_association(
            gene=gene,
            disease=disease,
            target_id=target_id,
            disease_id=disease_id,
            overall=float(row.get("score") or 0.0),
            datatype_scores=row.get("datatypeScores") or [],
            datasource_scores=row.get("datasourceScores") or [],
        )

    def _project_association(
        self,
        *,
        gene: str,
        disease: str,
        target_id: str,
        disease_id: str,
        overall: float,
        datatype_scores: list[dict[str, Any]],
        datasource_scores: list[dict[str, Any]],
    ) -> list[EvidenceItem]:
        """
        Project Open Targets association pillars into BioLead evidence objects.
        Datasource scores are required because datatype aggregates alone under-represent
        convergent genetics + clinical pharmacology for Driver decisions.
        """
        dt = {str(s.get("id")): float(s.get("score") or 0.0) for s in datatype_scores}
        ds = {str(s.get("id")): float(s.get("score") or 0.0) for s in datasource_scores}
        url = f"https://platform.opentargets.org/evidence/{target_id}/{disease_id}"
        items: list[EvidenceItem] = []

        def add(
            *,
            suffix: str,
            category: EvidenceType,
            label: str,
            value: float,
            min_keep: float = 0.08,
            stance: str = "supports",
            direction: str = "unresolved",
        ) -> None:
            if value < min_keep:
                return
            items.append(
                EvidenceItem(
                    id=f"ot-{gene.lower()}-{suffix}",
                    category=category,
                    title=f"Open Targets {label} for {gene}",
                    summary=(
                        f"Open Targets reports a {label} score of {value:.2f} between {gene} and {disease} "
                        f"(overall association {overall:.2f})."
                    ),
                    source_name=self.name,
                    source_url=url,
                    quality=EvidenceQuality.HIGH if value >= 0.65 else EvidenceQuality.MODERATE,
                    stance=stance,  # type: ignore[arg-type]
                    direction=direction,  # type: ignore[arg-type]
                    directness=min(0.98, max(0.35, value)),
                    independent_key=f"ot-{suffix}",
                    raw_source=f"Open Targets target={target_id}, disease={disease_id}, source={suffix}",
                )
            )

        genetics = max(
            dt.get("genetic_association", 0.0),
            dt.get("genetic_literature", 0.0),
            ds.get("gwas_credible_sets", 0.0),
            ds.get("gene_burden", 0.0),
            ds.get("genomics_england", 0.0),
            ds.get("eva", 0.0),
            ds.get("ot_genetics_portal", 0.0),
        )
        clinical = max(
            dt.get("clinical", 0.0),
            dt.get("known_drug", 0.0),
            ds.get("clinical_precedence", 0.0),
            ds.get("chembl", 0.0),
        )
        animal = max(dt.get("animal_model", 0.0), ds.get("impc", 0.0))
        pathway = max(dt.get("affected_pathway", 0.0), ds.get("reactome", 0.0))
        expression = max(dt.get("rna_expression", 0.0), ds.get("expression_atlas", 0.0))
        literature = max(dt.get("literature", 0.0), ds.get("europepmc", 0.0))
        gwas = ds.get("gwas_credible_sets", 0.0)
        burden = ds.get("gene_burden", 0.0)

        add(suffix="genetics", category=EvidenceType.HUMAN_GENETICS, label="human genetics", value=genetics)
        # Strong credible-set genetics is treated as locus-to-gene style support.
        add(
            suffix="gwas-credible-sets",
            category=EvidenceType.COLOCALIZATION,
            label="GWAS credible-set genetics",
            value=gwas,
            min_keep=0.35,
        )
        add(
            suffix="gene-burden",
            category=EvidenceType.MENDELIAN_RANDOMIZATION,
            label="gene-burden genetic support",
            value=burden,
            min_keep=0.45,
        )
        add(
            suffix="clinical",
            category=EvidenceType.CLINICAL_PHARMACOLOGY,
            label="clinical pharmacology",
            value=clinical,
            direction="inhibit" if clinical >= 0.5 else "unresolved",
        )
        # Target-engaging clinical precedence implies pharmacological perturbation support.
        if clinical >= 0.70:
            add(
                suffix="clinical-perturbation",
                category=EvidenceType.CAUSAL_PERTURBATION,
                label="clinical target-engagement / perturbation",
                value=min(0.95, clinical * 0.9),
                direction="inhibit",
                min_keep=0.0,
            )
        add(
            suffix="animal-model",
            category=EvidenceType.CAUSAL_PERTURBATION,
            label="animal-model perturbation",
            value=animal,
        )
        add(
            suffix="pathway",
            category=EvidenceType.MECHANISTIC_COHERENCE,
            label="pathway / mechanism",
            value=pathway,
        )
        add(
            suffix="expression",
            category=EvidenceType.DIFFERENTIAL_EXPRESSION,
            label="RNA expression",
            value=expression,
        )
        add(
            suffix="literature",
            category=EvidenceType.LITERATURE,
            label="literature",
            value=literature,
        )

        # Association-only cases: explicit causal-gap counter-evidence enables Passenger.
        strong_causal = max(genetics, clinical, animal, gwas, burden) >= 0.30
        correlative = max(expression, literature)
        if correlative >= 0.20 and not strong_causal:
            add(
                suffix="causal-gap",
                category=EvidenceType.CAUSAL_PERTURBATION,
                label="causal evidence gap",
                value=max(0.55, correlative),
                stance="contradicts",
                min_keep=0.0,
            )
            items[-1] = items[-1].model_copy(
                update={
                    "title": f"No disease-relevant causal rescue evidence identified for {gene}",
                    "summary": (
                        f"Open Targets association for {gene} in {disease} is dominated by correlative "
                        f"signals (expression/literature) without strong genetics, clinical pharmacology, "
                        f"or animal-model causal pillars."
                    ),
                }
            )
        return items


class EuropePMCAdapter(EvidenceAdapter):
    name = "Europe PMC"
    endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, client: httpx.AsyncClient, cache: EvidenceCache) -> None:
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
    """
    Turns raw GWAS Catalog v2 associations into a *single*, information-rich
    card. We only emit a card if it actually carries value:
      - the trait matches the query disease, OR
      - the association is at/near genome-wide significance (p < 5e-8).
    Everything else is dropped — no bare "mapped near <gene>" noise.
    """

    name = "GWAS Catalog"
    endpoint = "https://www.ebi.ac.uk/gwas/rest/api/v2/associations"
    GENOME_WIDE_SIG = 5e-8

    def __init__(self, client: httpx.AsyncClient, cache: EvidenceCache) -> None:
        self.client = client
        self.cache = cache

    @staticmethod
    def _efo_trait(association: dict[str, Any]) -> tuple[str, str | None]:
        """Return (human_readable_trait, efo_id)."""
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
    cache = get_evidence_cache()
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
