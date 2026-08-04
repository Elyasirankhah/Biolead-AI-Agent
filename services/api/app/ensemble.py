from __future__ import annotations

from collections import Counter
from typing import Literal

from .models import ScoreCard

Verdict = Literal["Driver", "Passenger", "Insufficient evidence"]
VALID_VERDICTS = {"Driver", "Passenger", "Insufficient evidence"}


def normalize_vote(value: object) -> Verdict | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned in VALID_VERDICTS:
        return cleaned  # type: ignore[return-value]
    lowered = cleaned.lower()
    if "insufficient" in lowered or "abstain" in lowered:
        return "Insufficient evidence"
    if "passenger" in lowered:
        return "Passenger"
    if "driver" in lowered:
        return "Driver"
    return None


def merge_ensemble_votes(
    deterministic: Verdict,
    advocate: Verdict | None,
    falsifier: Verdict | None,
    scorecard: ScoreCard,
    *,
    require_llm_voters: bool = True,
) -> tuple[Verdict, dict]:
    """
    Hybrid ensemble (required path):
    - deterministic rubric always votes
    - LLM advocate + falsifier must both vote when require_llm_voters=True
    - majority wins, with evidence guardrails
    - disagreement / missing voters / weak pillars → abstain
    """
    if require_llm_voters and (advocate is None or falsifier is None):
        trace = {
            "deterministic": deterministic,
            "advocate": advocate,
            "falsifier": falsifier,
            "votes": [deterministic],
            "final": "Insufficient evidence",
            "agreement": False,
            "policy": "ensemble_required_voters_unavailable",
        }
        return "Insufficient evidence", trace

    votes: list[Verdict] = [deterministic]
    if advocate is not None:
        votes.append(advocate)
    if falsifier is not None:
        votes.append(falsifier)

    counts = Counter(votes)
    top, top_count = counts.most_common(1)[0]
    unanimous = len(set(votes)) == 1
    majority = top_count >= 2 if len(votes) >= 2 else True

    final: Verdict
    reason: str

    if len(votes) == 1:
        final = deterministic
        reason = "deterministic_only"
    elif unanimous:
        final = deterministic
        reason = "unanimous"
    elif majority:
        final = top
        reason = "majority"
        if final == "Driver" and (
            scorecard.independent_pillars < 2
            or scorecard.causality.value < 58
            or scorecard.evidence_quality.value < 35
        ):
            final = "Insufficient evidence"
            reason = "majority_driver_blocked_scientific_threshold"
        elif (
            final == "Passenger"
            and deterministic == "Driver"
            and scorecard.independent_pillars >= 2
            and scorecard.causality.value >= 58
        ):
            final = "Insufficient evidence"
            reason = "majority_passenger_vs_strong_driver_abstain"
    else:
        final = "Insufficient evidence"
        reason = "disagreement_abstain"

    trace = {
        "deterministic": deterministic,
        "advocate": advocate,
        "falsifier": falsifier,
        "votes": votes,
        "final": final,
        "agreement": unanimous if len(votes) > 1 else True,
        "policy": reason,
    }
    return final, trace


def adjust_confidence(base: int, verdict: Verdict, trace: dict) -> int:
    confidence = base
    if trace.get("policy") == "unanimous" and len(trace.get("votes", [])) >= 3:
        confidence = min(95, confidence + 6)
    elif trace.get("policy") in {
        "disagreement_abstain",
        "majority_passenger_vs_strong_driver_abstain",
        "majority_driver_blocked_weak_pillars",
        "majority_driver_blocked_scientific_threshold",
        "ensemble_required_voters_unavailable",
    }:
        confidence = min(confidence, 58)
    if verdict == "Insufficient evidence":
        confidence = min(confidence, 69)
    return int(confidence)
