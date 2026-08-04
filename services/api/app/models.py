from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


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


class AnalysisRequest(BaseModel):
    disease: str = Field(min_length=2, max_length=120)
    genes: list[str] = Field(min_length=1, max_length=5)
    tissue: str = Field(default="skin", max_length=80)
    intervention_direction: Literal["inhibit", "activate", "unknown"] = "unknown"
    mode: Literal["demo", "live"] = "demo"


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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    research_use_only: bool = True


class RunResponse(BaseModel):
    run_id: str
    disease: str
    results: list[AnalysisResult]
