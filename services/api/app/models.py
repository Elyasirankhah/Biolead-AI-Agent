from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from .feedback_models import FeedbackApplySummary


class EvidenceType(str, Enum):
    MENDELIAN_RANDOMIZATION = "mendelian_randomization"
    COLOCALIZATION = "colocalization"
    HUMAN_GENETICS = "human_genetics"
    CAUSAL_PERTURBATION = "causal_perturbation"
    CLINICAL_PHARMACOLOGY = "clinical_pharmacology"
    MECHANISTIC_COHERENCE = "mechanistic_coherence"
    DIFFERENTIAL_EXPRESSION = "differential_expression"
    LITERATURE = "literature"


class EvidenceQuality(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class EvidenceItem(BaseModel):
    id: str
    category: EvidenceType
    title: str
    summary: str
    source_name: str
    source_url: HttpUrl
    citation: str | None = None
    quality: EvidenceQuality
    stance: Literal["supports", "contradicts", "neutral"] = "supports"
    direction: Literal["inhibit", "activate", "loss_of_function", "gain_of_function", "unresolved"] = "unresolved"
    tissue_relevant: bool = True
    directness: float = Field(default=0.7, ge=0, le=1)
    independent_key: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    excerpt: str | None = None
    raw_source: str | None = None
    provenance_status: Literal["accepted", "rejected", "unverified"] = "unverified"
    provenance_reason: str | None = None


class AnalysisRequest(BaseModel):
    disease: str = Field(min_length=2, max_length=120)
    genes: list[str] = Field(min_length=1, max_length=5)
    tissue: str = Field(default="skin", max_length=80)
    intervention_direction: Literal["inhibit", "activate", "unknown"] = "unknown"
    mode: Literal["demo", "live"] = "demo"
    refresh: bool = False


class DimensionScore(BaseModel):
    value: int = Field(ge=0, le=100)
    rationale: str


class ScoreCard(BaseModel):
    causality: DimensionScore
    actionability: DimensionScore
    evidence_quality: DimensionScore
    contradiction_penalty: int = Field(ge=0, le=100)
    independent_pillars: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    scoring_version: str = "1.1.0"


class AgentVoteTrace(BaseModel):
    role: Literal["advocate", "falsifier"]
    vote: Literal["Driver", "Passenger", "Insufficient evidence"]
    causal_pillars: list[
        Literal[
            "mendelian_randomization",
            "colocalization",
            "human_genetics",
            "causal_perturbation",
            "clinical_pharmacology",
            "mechanistic_coherence",
        ]
    ] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    alternative_explanation: str = ""
    rationale: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)
    guardrail_actions: list[str] = Field(default_factory=list)


class EnsembleTrace(BaseModel):
    deterministic: Literal["Driver", "Passenger", "Insufficient evidence"]
    advocate: Literal["Driver", "Passenger", "Insufficient evidence"] | None = None
    falsifier: Literal["Driver", "Passenger", "Insufficient evidence"] | None = None
    advocate_detail: AgentVoteTrace | None = None
    falsifier_detail: AgentVoteTrace | None = None
    final: Literal["Driver", "Passenger", "Insufficient evidence"]
    agreement: bool = True
    policy: str = "deterministic_only"


class ConflictRecord(BaseModel):
    conflict_id: str
    evidence_a_id: str
    evidence_b_id: str
    classification: Literal["hard", "contextual"]
    conflict_type: str
    summary: str
    resolution: str = ""


class FalsificationGate(BaseModel):
    status: Literal["PASSED", "UNRESOLVED", "SKIPPED"]
    hypothesis_tested: str
    counter_hypotheses: list[str] = Field(default_factory=list)
    counter_queries: list[str] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    strongest_counter_evidence_id: str | None = None
    resolution: str = ""
    residual_uncertainty: str = ""
    gate_completed: bool = True


class DecisionLedger(BaseModel):
    """Scientist-facing auditable decision object (product surface)."""

    hypothesis: str
    therapeutic_direction: Literal["inhibit", "activate", "unresolved"]
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    hard_contradictions_unresolved: int = Field(default=0, ge=0)
    falsification: FalsificationGate
    what_would_change: list[str] = Field(default_factory=list)
    snapshot_id: str
    content_hash: str = ""
    rules_version: str = "score:1.1.0|prov:1.0.0|falsify:1.0.0|ensemble:1.0.0"
    scoring_version: str = "1.1.0"
    provenance_version: str = "1.0.0"
    falsification_version: str = "1.0.0"
    reproducible: bool = True
    evidence_count: int = Field(default=0, ge=0)
    supporting_count: int = Field(default=0, ge=0)
    contradicting_count: int = Field(default=0, ge=0)
    provenance_accepted: int = Field(default=0, ge=0)
    provenance_rejected: int = Field(default=0, ge=0)
    rejected_evidence_ids: list[str] = Field(default_factory=list)


class StageTrace(BaseModel):
    id: str
    label: str
    status: Literal["ok", "degraded", "skipped", "failed"]
    detail: str
    duration_ms: int = 0


class PipelineTrace(BaseModel):
    stages: list[StageTrace] = Field(default_factory=list)
    retries: int = 0
    source_errors: list[str] = Field(default_factory=list)
    thin_evidence: bool = False
    mode: Literal["demo", "live"] = "demo"
    rag_queries: list[str] = Field(default_factory=list)
    rag_sources_hit: list[str] = Field(default_factory=list)
    rag_sources_failed: list[str] = Field(default_factory=list)
    rag_cache_mode: str = "shared"
    rag_refreshed: bool = False
    rag_literature_kept: int = 0
    rag_structured_kept: int = 0
    feedback_applied: int = 0
    feedback_irrelevant: int = 0
    feedback_wrong_direction: int = 0
    feedback_important: int = 0


class AnalysisResult(BaseModel):
    run_id: str
    gene: str
    disease: str
    tissue: str
    verdict: Literal["Driver", "Passenger", "Insufficient evidence"]
    confidence: int = Field(ge=0, le=100)
    recommended_direction: Literal["inhibit", "activate", "unresolved"]
    scorecard: ScoreCard
    executive_summary: str
    driver_case: list[str]
    passenger_case: list[str]
    next_experiments: list[str]
    evidence: list[EvidenceItem]
    limitations: list[str]
    ensemble: EnsembleTrace | None = None
    decision_ledger: DecisionLedger | None = None
    pipeline: PipelineTrace | None = None
    feedback_summary: FeedbackApplySummary | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    research_use_only: bool = True


class RunResponse(BaseModel):
    run_id: str
    disease: str
    results: list[AnalysisResult]
