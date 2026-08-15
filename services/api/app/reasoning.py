from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from .ensemble import adjust_confidence, merge_ensemble_votes, normalize_vote
from .falsification import run_falsification
from .feedback import apply_scientist_feedback
from .feedback_models import FeedbackRecord
from .ledger import build_decision_ledger
from .models import AgentVoteTrace, AnalysisResult, EnsembleTrace, EvidenceItem, EvidenceType
from .provenance import apply_provenance_gate
from .scoring import CAUSAL_CATEGORIES, score_evidence

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _read_prompt(name: str, fallback: str) -> str:
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return fallback


class NarrativeProvider(Protocol):
    async def synthesize(self, payload: dict) -> dict | None: ...

    async def vote(self, role: str, payload: dict) -> dict | None: ...


class OpenAICompatibleProvider:
    """Optional structured-output provider for OpenAI-compatible APIs."""

    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.api_key = os.getenv("LLM_API_KEY")
        self.model = os.getenv("LLM_MODEL", "gpt-5-mini")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _complete(self, prompt: str) -> dict | None:
        if not self.api_key:
            return None
        body: dict = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        # Some models (e.g. gpt-5-mini) only allow the default temperature.
        if not self.model.startswith(("gpt-5", "o1", "o3", "o4")):
            body["temperature"] = 0

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
                timeout=60,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Plain-text chat (Clara). Uses the same LLM_API_KEY / LLM_MODEL as ensemble voters."""
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not configured")
        body: dict = {
            "model": self.model,
            "messages": messages,
        }
        if self.model.startswith(("gpt-5", "o1", "o3", "o4")):
            body["max_completion_tokens"] = 800
        else:
            body["temperature"] = 0.3
            body["max_tokens"] = 500

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
                timeout=60,
            )
            response.raise_for_status()
            return (response.json()["choices"][0]["message"]["content"] or "").strip()

    async def synthesize(self, payload: dict) -> dict | None:
        prompt = (
            _read_prompt(
                "critic_v1.txt",
                "You are BioLead's scientific critic. Use only supplied evidence. Return JSON.",
            )
            + "\n\nReturn JSON with executive_summary, driver_case, passenger_case, next_experiments.\n"
            + json.dumps(payload)
        )
        return await self._complete(prompt)

    async def vote(self, role: str, payload: dict) -> dict | None:
        if role == "advocate":
            instructions = _read_prompt(
                "advocate_v1.txt",
                (
                    "You are BioLead's driver advocate. Argue the strongest causal case allowed by the evidence. "
                    "Vote Driver only with convergent causal pillars. Otherwise vote Insufficient evidence or Passenger."
                ),
            )
        else:
            instructions = _read_prompt(
                "falsifier_v1.txt",
                (
                    "You are BioLead's falsifier. Actively attack unsupported causal claims. "
                    "Prefer Passenger or Insufficient evidence unless causal pillars clearly converge."
                ),
            )
        prompt = f"{instructions}\n\nINPUT PAYLOAD\n{json.dumps(payload)}"
        return await self._complete(prompt)


def _recommended_direction(items: list[EvidenceItem]) -> str:
    directions = Counter(
        item.direction
        for item in items
        if item.stance == "supports" and item.direction in {"inhibit", "activate"}
    )
    if not directions:
        return "unresolved"
    direction, count = directions.most_common(1)[0]
    return direction if count >= 2 or any(
        item.direction == direction
        and item.category == EvidenceType.CLINICAL_PHARMACOLOGY
        and item.stance == "supports"
        for item in items
    ) else "unresolved"


def _default_narrative(gene: str, disease: str, verdict: str, items: list[EvidenceItem]) -> dict:
    supports = [item for item in items if item.stance == "supports"]
    contradicts = [item for item in items if item.stance == "contradicts"]
    strongest = sorted(supports, key=lambda item: (item.quality.value == "high", item.directness), reverse=True)
    driver_case = [item.title for item in strongest[:3]]
    passenger_case = [item.title for item in contradicts[:3]]
    if not passenger_case:
        passenger_case = [
            "Correlation and literature volume are not treated as causal proof.",
            "Tissue, intervention direction, and independent replication still require review.",
        ]
    if verdict == "Driver":
        summary = (
            f"{gene} is classified as a likely driver of {disease} because independent causal "
            "pillars converge, with counter-evidence explicitly penalized."
        )
    elif verdict == "Passenger":
        summary = (
            f"{gene} is classified as passenger-like for {disease}: disease-state association "
            "is present, but direct causal and rescue evidence is absent or contradictory."
        )
    else:
        summary = (
            f"BioLead abstains for {gene} in {disease}. The evidence does not yet satisfy the "
            "minimum independent causal-pillar threshold."
        )
    return {
        "executive_summary": summary,
        "driver_case": driver_case or ["No supporting evidence was retrieved."],
        "passenger_case": passenger_case,
        "next_experiments": [
            f"Perturb {gene} in disease-relevant primary skin cells and measure phenotype rescue.",
            "Validate direction of effect with orthogonal CRISPR and pharmacologic perturbations.",
            "Test whether human disease and molecular-QTL signals colocalize in relevant tissue.",
        ],
    }


def _ground_generated_narrative(generated: dict, items: list[EvidenceItem], fallback: dict) -> dict:
    """Keep claim lists source-grounded even when an optional LLM is enabled."""
    titles = {item.title for item in items}
    grounded_driver = [claim for claim in generated.get("driver_case", []) if claim in titles]
    grounded_passenger = [claim for claim in generated.get("passenger_case", []) if claim in titles]
    experiments = [
        item for item in generated.get("next_experiments", [])
        if isinstance(item, str) and 10 <= len(item) <= 240
    ][:4]
    summary = generated.get("executive_summary")
    return {
        "executive_summary": summary if isinstance(summary, str) and len(summary) <= 700 else fallback["executive_summary"],
        "driver_case": grounded_driver or fallback["driver_case"],
        "passenger_case": grounded_passenger or fallback["passenger_case"],
        "next_experiments": experiments or fallback["next_experiments"],
    }


def _ground_vote_trace(
    raw: dict,
    role: str,
    items: list[EvidenceItem],
    scorecard,
) -> AgentVoteTrace | None:
    """Validate the LLM's concise decision trace against supplied evidence."""
    vote = normalize_vote(raw.get("vote"))
    if vote is None or role not in {"advocate", "falsifier"}:
        return None

    by_id = {item.id: item for item in items}
    valid_ids = set(by_id)
    guardrail_actions: list[str] = []

    def grounded_ids(key: str, stance: str | None = None) -> list[str]:
        requested = raw.get(key, [])
        if not isinstance(requested, list):
            guardrail_actions.append(f"{key}_rejected_not_list")
            return []
        unique = []
        for evidence_id in requested:
            if not isinstance(evidence_id, str) or evidence_id not in valid_ids:
                guardrail_actions.append(f"{key}_removed_unknown_id")
                continue
            if stance and by_id[evidence_id].stance != stance:
                guardrail_actions.append(f"{key}_removed_stance_mismatch")
                continue
            if evidence_id not in unique:
                unique.append(evidence_id)
        return unique[:8]

    supporting_ids = grounded_ids("supporting_evidence_ids", "supports")
    contradicting_ids = grounded_ids("contradicting_evidence_ids", "contradicts")

    evidenced_pillars = {
        by_id[evidence_id].category.value
        for evidence_id in supporting_ids
        if by_id[evidence_id].category in CAUSAL_CATEGORIES
    }
    requested_pillars = raw.get("causal_pillars", [])
    if not isinstance(requested_pillars, list):
        requested_pillars = []
        guardrail_actions.append("causal_pillars_rejected_not_list")
    expanded_pillars: list[str] = []
    for pillar in requested_pillars:
        if isinstance(pillar, str):
            expanded_pillars.extend(part.strip() for part in pillar.split("|") if part.strip())
    if expanded_pillars != requested_pillars:
        guardrail_actions.append("causal_pillars_normalized")
    pillars = [
        pillar
        for pillar in dict.fromkeys(expanded_pillars)
        if isinstance(pillar, str) and pillar in evidenced_pillars
    ]
    if len(pillars) != len(expanded_pillars):
        guardrail_actions.append("unsupported_causal_pillars_removed")

    correlational_support = any(
        by_id[evidence_id].category
        in {EvidenceType.DIFFERENTIAL_EXPRESSION, EvidenceType.LITERATURE}
        for evidence_id in supporting_ids
    )
    if vote == "Driver" and (
        len(pillars) < 2
        or scorecard.independent_pillars < 2
        or scorecard.causality.value < 58
        or scorecard.evidence_quality.value < 35
    ):
        vote = "Insufficient evidence"
        guardrail_actions.append("driver_downgraded_scientific_threshold")
    elif vote == "Passenger" and not (correlational_support and contradicting_ids):
        vote = "Insufficient evidence"
        guardrail_actions.append("passenger_downgraded_missing_counterevidence")

    missing = raw.get("missing_requirements", [])
    missing_requirements = (
        [item[:200] for item in missing if isinstance(item, str) and item.strip()][:6]
        if isinstance(missing, list)
        else []
    )
    alternative = raw.get("alternative_explanation", "")
    alternative_explanation = alternative[:400] if isinstance(alternative, str) else ""
    rationale = raw.get("rationale", "")
    rationale = rationale[:500] if isinstance(rationale, str) else ""
    confidence = raw.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
        guardrail_actions.append("confidence_reset_invalid")
    confidence = max(0.0, min(1.0, float(confidence)))
    if guardrail_actions:
        confidence = min(confidence, 0.69)

    return AgentVoteTrace(
        role=role,
        vote=vote,
        causal_pillars=pillars,
        supporting_evidence_ids=supporting_ids,
        contradicting_evidence_ids=contradicting_ids,
        missing_requirements=missing_requirements,
        alternative_explanation=alternative_explanation,
        rationale=rationale,
        confidence=confidence,
        guardrail_actions=list(dict.fromkeys(guardrail_actions)),
    )


def _evidence_payload(gene: str, disease: str, scorecard, items: list[EvidenceItem], det_verdict: str) -> dict:
    return {
        "gene": gene,
        "disease": disease,
        "deterministic_verdict": det_verdict,
        "scorecard": scorecard.model_dump(),
        "evidence": [
            {
                "id": item.id,
                "title": item.title,
                "summary": item.summary,
                "stance": item.stance,
                "category": item.category,
                "quality": item.quality,
                "directness": item.directness,
                "tissue_relevant": item.tissue_relevant,
                "independent_key": item.independent_key,
            }
            for item in items
        ],
    }


async def build_result(
    disease: str,
    gene: str,
    tissue: str,
    items: list[EvidenceItem],
    provider: NarrativeProvider | None = None,
    run_id: str | None = None,
    source_errors: list[str] | None = None,
    mode: str | None = None,
    feedbacks: list[FeedbackRecord] | None = None,
) -> AnalysisResult:
    accepted, rejected = apply_provenance_gate(items)
    feedback_kept, feedback_removed, feedback_summary = apply_scientist_feedback(
        accepted, feedbacks or []
    )
    accepted = feedback_kept
    rejected = rejected + feedback_removed
    scorecard, det_verdict, confidence = score_evidence(accepted)
    advocate_vote = None
    falsifier_vote = None
    advocate_detail = None
    falsifier_detail = None
    narrative = _default_narrative(gene, disease, det_verdict, accepted)
    is_demo = (mode or "").strip().lower() == "demo"
    require_llm = not is_demo and os.getenv("ENSEMBLE_REQUIRED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    # Demo is the frozen, reproducible presentation path. Do not let optional
    # model votes or generated prose change its verdict, snapshot, or wording.
    llm_ready = bool(not is_demo and provider and getattr(provider, "enabled", False))
    if llm_ready:
        payload = _evidence_payload(gene, disease, scorecard, accepted, det_verdict)
        advocate_raw, falsifier_raw = await asyncio.gather(
            provider.vote("advocate", payload),
            provider.vote("falsifier", payload),
            return_exceptions=True,
        )
        if isinstance(advocate_raw, dict):
            advocate_detail = _ground_vote_trace(
                advocate_raw, "advocate", accepted, scorecard
            )
            advocate_vote = advocate_detail.vote if advocate_detail else None
            grounded = _ground_generated_narrative(advocate_raw, accepted, narrative)
            narrative = {**narrative, **{k: grounded[k] for k in grounded if grounded[k]}}
        if isinstance(falsifier_raw, dict):
            falsifier_detail = _ground_vote_trace(
                falsifier_raw, "falsifier", accepted, scorecard
            )
            falsifier_vote = falsifier_detail.vote if falsifier_detail else None
            grounded_f = _ground_generated_narrative(falsifier_raw, accepted, narrative)
            if grounded_f["passenger_case"] and grounded_f["passenger_case"] != narrative.get("passenger_case"):
                narrative["passenger_case"] = grounded_f["passenger_case"]
            if grounded_f.get("next_experiments"):
                merged = list(dict.fromkeys(narrative["next_experiments"] + grounded_f["next_experiments"]))[:4]
                narrative["next_experiments"] = merged

    verdict, trace = merge_ensemble_votes(
        det_verdict,
        advocate_vote,
        falsifier_vote,
        scorecard,
        require_llm_voters=require_llm,
    )
    confidence = adjust_confidence(confidence, verdict, trace)

    direction = _recommended_direction(accepted)
    falsification = run_falsification(
        gene=gene.upper(),
        disease=disease,
        direction=direction,
        items=accepted,
        ensemble_policy=str(trace.get("policy")),
    )
    # Mandatory gate: unresolved hard conflicts cannot remain high-confidence Driver.
    if verdict == "Driver" and falsification.blocks_driver:
        verdict = "Insufficient evidence"
        confidence = min(confidence, 69)
        trace = {**trace, "policy": f"{trace.get('policy')}+falsification_hard_conflict_block"}
        limitations_note = (
            "Falsification gate blocked Driver: unresolved hard contradiction(s) remain."
        )
    else:
        limitations_note = None

    # Refresh default summary if verdict changed from deterministic-only narrative.
    if verdict != det_verdict and (
        not narrative.get("executive_summary")
        or "classified" in narrative["executive_summary"]
        or "abstains" in narrative["executive_summary"]
    ):
        refreshed = _default_narrative(gene, disease, verdict, accepted)
        narrative["executive_summary"] = refreshed["executive_summary"]

    if advocate_vote and falsifier_vote and advocate_vote != falsifier_vote:
        narrative["executive_summary"] = (
            f"{narrative['executive_summary']} Ensemble note: advocate voted {advocate_vote}, "
            f"falsifier voted {falsifier_vote}; final policy={trace['policy']}."
        )[:700]

    if is_demo:
        ensemble_limitation = (
            "Demo mode uses the frozen deterministic decision path; LLM voters are intentionally skipped."
        )
    elif advocate_vote is not None and falsifier_vote is not None:
        ensemble_limitation = (
            "Final verdict uses the hybrid ensemble: deterministic rubric + LLM advocate + LLM falsifier."
        )
    elif require_llm:
        ensemble_limitation = (
            "Hybrid ensemble was required, but unavailable voters forced an abstention-safe verdict."
        )
    else:
        ensemble_limitation = (
            "Final verdict uses the deterministic rubric because both LLM voters were not available."
        )
    limitations = [
        "Research-use-only prioritization; not clinical or experimental validation.",
        "Public sources differ in recency, ancestry, tissue coverage, and publication bias.",
        "A missing result is not proof that no evidence exists.",
        ensemble_limitation,
        "Only provenance-accepted evidence can influence the verdict (fail closed).",
        "Falsification is mandatory: BioLead will not issue a causal verdict without attempting disproof.",
        "Decision snapshots are versioned: identical normalized evidence + rules produce the same content hash.",
    ]
    if limitations_note:
        limitations.append(limitations_note)
    if source_errors:
        limitations.append("Unavailable live sources: " + ", ".join(source_errors))
    if rejected:
        limitations.append(
            f"Provenance gate rejected {len(rejected)} evidence item(s): "
            + ", ".join(f"{item.id} ({item.provenance_reason})" for item in rejected[:4])
        )
    if feedback_summary.applied:
        limitations.append(
            f"Scientist feedback applied to {feedback_summary.applied} evidence item(s) "
            f"(irrelevant={feedback_summary.irrelevant}, wrong_direction={feedback_summary.wrong_direction}, "
            f"important={feedback_summary.important})."
        )
    if not accepted:
        limitations.append("No provenance-accepted evidence items were available for this query.")
    if is_demo:
        pass
    elif advocate_vote is None or falsifier_vote is None:
        if require_llm:
            limitations.append(
                "Ensemble voters unavailable; ENSEMBLE_REQUIRED forced abstention to Insufficient evidence."
            )
        else:
            limitations.append("LLM voters unavailable; deterministic rubric only.")

    result_run_id = run_id or str(uuid4())
    ledger = build_decision_ledger(
        gene=gene.upper(),
        disease=disease,
        tissue=tissue,
        verdict=verdict,
        direction=direction,
        items=accepted,
        scorecard=scorecard,
        ensemble_policy=str(trace.get("policy")),
        rejected_items=rejected,
        mode=mode,
    )

    # Keep rejected items visible for audit, after accepted ones.
    display_evidence = accepted + rejected

    return AnalysisResult(
        run_id=result_run_id,
        gene=gene.upper(),
        disease=disease,
        tissue=tissue,
        verdict=verdict,
        confidence=confidence,
        recommended_direction=direction,
        scorecard=scorecard,
        evidence=display_evidence,
        limitations=limitations,
        decision_ledger=ledger,
        feedback_summary=feedback_summary if feedback_summary.applied else None,
        ensemble=EnsembleTrace(
            deterministic=det_verdict,
            advocate=advocate_vote,
            falsifier=falsifier_vote,
            advocate_detail=advocate_detail,
            falsifier_detail=falsifier_detail,
            final=verdict,
            agreement=bool(trace.get("agreement")),
            policy=str(trace.get("policy")),
        ),
        **narrative,
    )
