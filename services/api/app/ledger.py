from __future__ import annotations

from .falsification import run_falsification, therapeutic_hypothesis
from .models import AnalysisResult, DecisionLedger, EvidenceItem, ScoreCard
from .snapshot import (
    FALSIFICATION_VERSION,
    PROVENANCE_VERSION,
    RULES_VERSION,
    SCORING_VERSION,
    build_decision_snapshot,
)


def _what_would_change(gene: str, disease: str, verdict: str) -> list[str]:
    if verdict == "Driver":
        return [
            f"Replicated human evidence that {gene} activity in the opposite direction protects from {disease}.",
            f"Disease-relevant intervention showing {gene} modulation worsens clinical phenotype.",
            "Unresolved hard contradiction between genetics and pharmacology in comparable context.",
        ]
    if verdict == "Passenger":
        return [
            f"Disease-relevant perturbation showing that changing {gene} activity alters {disease} phenotype.",
            "Independent human genetics assigning causality to this gene (not a neighbor).",
            "Target-engaging clinical or pharmacological rescue evidence in humans.",
        ]
    return [
        "At least two independent causal evidence families with verified provenance.",
        f"Clear therapeutic direction for {gene} in {disease}-relevant human context.",
        "Human genetics and/or clinical pharmacology that converges without hard contradiction.",
    ]


def build_decision_ledger(
    *,
    gene: str,
    disease: str,
    tissue: str = "skin",
    verdict: str,
    direction: str,
    items: list[EvidenceItem],
    scorecard: ScoreCard,
    ensemble_policy: str | None = None,
    rejected_items: list[EvidenceItem] | None = None,
    mode: str | None = None,
) -> DecisionLedger:
    supports = [item for item in items if item.stance == "supports"]
    contradicts = [item for item in items if item.stance == "contradicts"]
    rejected = rejected_items or []
    falsification = run_falsification(
        gene=gene,
        disease=disease,
        direction=direction,
        items=items,
        ensemble_policy=ensemble_policy,
    )
    hypothesis = therapeutic_hypothesis(gene, disease, direction)
    snap = build_decision_snapshot(
        gene=gene,
        disease=disease,
        tissue=tissue,
        direction=direction,
        verdict=verdict,
        accepted_items=items,
        mode=mode,
    )

    return DecisionLedger(
        hypothesis=hypothesis,
        therapeutic_direction=direction,  # type: ignore[arg-type]
        evidence_for=[item.id for item in supports],
        evidence_against=[item.id for item in contradicts],
        hard_contradictions_unresolved=falsification.hard_unresolved,
        falsification=falsification.gate,
        what_would_change=_what_would_change(gene, disease, verdict),
        snapshot_id=snap["snapshot_id"],
        content_hash=snap["content_hash"],
        rules_version=RULES_VERSION,
        scoring_version=scorecard.scoring_version or SCORING_VERSION,
        provenance_version=PROVENANCE_VERSION,
        falsification_version=FALSIFICATION_VERSION,
        reproducible=True,
        evidence_count=len(items),
        supporting_count=len(supports),
        contradicting_count=len(contradicts),
        provenance_accepted=len(items),
        provenance_rejected=len(rejected),
        rejected_evidence_ids=[item.id for item in rejected],
    )


def attach_ledger(result: AnalysisResult) -> AnalysisResult:
    """Helper for tests — rebuild ledger onto an existing result."""
    ledger = build_decision_ledger(
        gene=result.gene,
        disease=result.disease,
        tissue=result.tissue,
        verdict=result.verdict,
        direction=result.recommended_direction,
        items=[item for item in result.evidence if item.provenance_status != "rejected"],
        scorecard=result.scorecard,
        ensemble_policy=result.ensemble.policy if result.ensemble else None,
        rejected_items=[item for item in result.evidence if item.provenance_status == "rejected"],
    )
    return result.model_copy(update={"decision_ledger": ledger})
