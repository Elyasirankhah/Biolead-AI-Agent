from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ConflictRecord, EvidenceItem, FalsificationGate

_MOUSE = re.compile(r"\b(mouse|mice|murine|knockout|embryonic|neonatal rodent)\b", re.I)
_HUMAN = re.compile(r"\b(human|patient|clinical|trial|pharmacolog|dupilumab|phase\s*[123])\b", re.I)
_ASSOC = re.compile(r"\b(associat|correlat|up-?regulat|expression|biomarker)\b", re.I)
_CAUSAL = re.compile(r"\b(causal|mendelian|colocali|perturb|rescue|efficacy|randomized)\b", re.I)


def therapeutic_hypothesis(gene: str, disease: str, direction: str) -> str:
    if direction == "inhibit":
        return f"Reducing {gene} activity/signaling should improve {disease}."
    if direction == "activate":
        return f"Restoring or increasing {gene} function should improve {disease}."
    return f"Modulating {gene} in a disease-relevant direction should improve {disease}."


def counter_hypotheses(gene: str, disease: str, direction: str) -> list[str]:
    if direction == "inhibit":
        return [
            f"{gene} inhibition worsens {disease}",
            f"{gene} activation improves {disease}",
            f"{gene} loss-of-function increases {disease} risk",
            f"Protective/risk signal near {gene} is explained by a different gene/pathway",
            "Supporting evidence fails to reproduce in independent systems",
            f"{gene} effect reverses in disease-relevant human tissue",
        ]
    if direction == "activate":
        return [
            f"{gene} activation worsens {disease}",
            f"{gene} inhibition improves {disease}",
            f"Loss of {gene} is protective for {disease}",
            f"Protective/risk signal near {gene} is explained by a different gene/pathway",
            "Supporting evidence fails to reproduce in independent systems",
            f"{gene} restoration fails in disease-relevant human tissue",
        ]
    return [
        f"Opposite-direction modulation of {gene} improves {disease}",
        f"{gene} association is downstream / non-causal for {disease}",
        "Protective or risk signal is explained by a different gene/pathway",
        "Supporting evidence fails to reproduce in independent systems",
    ]


def counter_search_queries(gene: str, disease: str, direction: str) -> list[str]:
    """Explicit falsification retrieval intents (shown in the product UI)."""
    if direction == "inhibit":
        return [
            f"{gene} inhibition worsens {disease}",
            f"{gene} activation improves {disease}",
            f"{gene} loss of function increases {disease} risk",
            f"{gene} blockade adverse {disease}",
            f"{gene} contradictory results {disease}",
        ]
    if direction == "activate":
        return [
            f"{gene} activation worsens {disease}",
            f"{gene} inhibition improves {disease}",
            f"{gene} loss of function protective {disease}",
            f"{gene} restoration failure {disease}",
            f"{gene} contradictory results {disease}",
        ]
    return [
        f"{gene} contradictory results {disease}",
        f"{gene} not causal {disease}",
        f"{gene} passenger biomarker {disease}",
    ]


def _blob(item: EvidenceItem) -> str:
    return " ".join(
        part
        for part in [item.title, item.summary, item.excerpt or "", item.raw_source or ""]
        if part
    )


def _context_tags(item: EvidenceItem) -> set[str]:
    text = _blob(item)
    tags: set[str] = set()
    if _MOUSE.search(text):
        tags.add("mouse")
    if _HUMAN.search(text):
        tags.add("human")
    if item.tissue_relevant:
        tags.add("tissue_relevant")
    if item.category.value in {
        "mendelian_randomization",
        "colocalization",
        "human_genetics",
        "causal_perturbation",
        "clinical_pharmacology",
    }:
        tags.add("causal_family")
    if item.category.value in {"differential_expression", "literature"}:
        tags.add("associative_family")
    if _ASSOC.search(text):
        tags.add("association_language")
    if _CAUSAL.search(text):
        tags.add("causal_language")
    if item.direction in {"inhibit", "activate"}:
        tags.add(f"dir:{item.direction}")
    return tags


def classify_pair(support: EvidenceItem, contradict: EvidenceItem) -> ConflictRecord:
    """Distinguish hard contradiction from contextual heterogeneity."""
    a_tags = _context_tags(support)
    b_tags = _context_tags(contradict)
    species_mismatch = ("mouse" in a_tags) != ("mouse" in b_tags) and (
        "mouse" in a_tags or "mouse" in b_tags
    ) and ("human" in a_tags or "human" in b_tags)
    family_mismatch = ("causal_family" in a_tags) != ("causal_family" in b_tags)
    direction_clash = (
        support.direction in {"inhibit", "activate"}
        and contradict.direction in {"inhibit", "activate"}
        and support.direction != contradict.direction
    )

    if species_mismatch or (
        family_mismatch and not direction_clash and contradict.quality.value != "high"
    ):
        classification = "contextual"
        conflict_type = "context"
        resolution = (
            "Contexts differ (species, intervention class, or evidence family). "
            "Treated as contextual heterogeneity, not an automatic hard contradiction."
        )
        summary = (
            f"Contextual conflict between '{support.title[:80]}' and '{contradict.title[:80]}'."
        )
    elif direction_clash or (
        support.stance == "supports"
        and contradict.stance == "contradicts"
        and "causal_family" in a_tags
        and "causal_family" in b_tags
    ):
        classification = "hard"
        conflict_type = "directionality" if direction_clash else "causal_polarity"
        resolution = "Unresolved hard conflict — comparable causal families with opposing implications."
        summary = (
            f"Hard conflict between '{support.title[:80]}' and '{contradict.title[:80]}'."
        )
    else:
        classification = "contextual"
        conflict_type = "replication_gap"
        resolution = (
            "Counter-evidence weakens confidence but does not match as a direct opposite "
            "finding in the same biological context."
        )
        summary = (
            f"Potential conflict between '{support.title[:80]}' and '{contradict.title[:80]}'."
        )

    return ConflictRecord(
        conflict_id=f"conf-{support.id}-{contradict.id}",
        evidence_a_id=support.id,
        evidence_b_id=contradict.id,
        classification=classification,  # type: ignore[arg-type]
        conflict_type=conflict_type,
        summary=summary,
        resolution=resolution,
    )


@dataclass
class FalsificationResult:
    gate: FalsificationGate
    conflicts: list[ConflictRecord]
    hard_unresolved: int
    blocks_driver: bool


def run_falsification(
    *,
    gene: str,
    disease: str,
    direction: str,
    items: list[EvidenceItem],
    ensemble_policy: str | None = None,
) -> FalsificationResult:
    """
    Mandatory falsification gate.
    A verdict path is incomplete unless this object exists.
    """
    hypothesis = therapeutic_hypothesis(gene, disease, direction)
    counters = counter_hypotheses(gene, disease, direction)
    queries = counter_search_queries(gene, disease, direction)

    supports = [item for item in items if item.stance == "supports"]
    contradicts = [item for item in items if item.stance == "contradicts"]
    strongest_counter = max(
        contradicts,
        key=lambda item: (item.quality.value == "high", item.directness),
        default=None,
    )

    conflicts: list[ConflictRecord] = []
    if supports and contradicts:
        # Pair strongest supports against each contradicting item (bounded).
        top_supports = sorted(
            supports,
            key=lambda item: (item.quality.value == "high", item.directness),
            reverse=True,
        )[:3]
        for contradict in contradicts[:4]:
            for support in top_supports[:2]:
                conflicts.append(classify_pair(support, contradict))

    # Deduplicate by evidence pair.
    seen: set[tuple[str, str]] = set()
    unique_conflicts: list[ConflictRecord] = []
    for conflict in conflicts:
        key = (conflict.evidence_a_id, conflict.evidence_b_id)
        if key in seen:
            continue
        seen.add(key)
        unique_conflicts.append(conflict)

    hard_unresolved = sum(1 for c in unique_conflicts if c.classification == "hard")
    blocks_driver = hard_unresolved > 0

    if not contradicts:
        status = "PASSED"
        residual = "Low from explicit counter-evidence; association/context gaps may remain."
        resolution = (
            "Falsification search executed. No contradicting evidence items were present "
            "after provenance filtering."
        )
    elif hard_unresolved == 0:
        status = "PASSED"
        residual = "Moderate — counter-evidence reviewed as contextual or non-blocking."
        resolution = (
            "Falsification search executed. Counter-evidence was classified as contextual "
            "heterogeneity or insufficient to block a causal call on its own."
        )
    else:
        status = "UNRESOLVED"
        residual = "Elevated — unresolved hard contradiction(s) remain."
        resolution = (
            "Falsification gate blocked a clean Driver path until hard conflicts are resolved "
            "or downgraded by stronger concordant evidence."
        )

    if ensemble_policy and "abstain" in ensemble_policy.lower():
        status = "UNRESOLVED"
        residual = "Ensemble policy forced caution (missing grounded voters or disagreement)."

    gate = FalsificationGate(
        status=status,  # type: ignore[arg-type]
        hypothesis_tested=hypothesis,
        counter_hypotheses=counters,
        counter_queries=queries,
        conflicts=unique_conflicts,
        strongest_counter_evidence_id=strongest_counter.id if strongest_counter else None,
        resolution=resolution,
        residual_uncertainty=residual,
        gate_completed=True,
    )
    return FalsificationResult(
        gate=gate,
        conflicts=unique_conflicts,
        hard_unresolved=hard_unresolved,
        blocks_driver=blocks_driver,
    )
