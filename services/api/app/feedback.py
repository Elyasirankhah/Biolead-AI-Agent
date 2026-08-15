from __future__ import annotations

from .feedback_models import FeedbackApplySummary, FeedbackRecord
from .models import EvidenceItem, EvidenceQuality


def apply_scientist_feedback(
    items: list[EvidenceItem],
    feedbacks: list[FeedbackRecord],
) -> tuple[list[EvidenceItem], list[EvidenceItem], FeedbackApplySummary]:
    """
    Apply scientist labels to evidence before scoring.
    - irrelevant → move out of scoring set (audit-only)
    - wrong_direction → flip inhibit/activate when possible
    - important → boost directness / quality
    Latest feedback per evidence_id wins.
    """
    latest: dict[str, FeedbackRecord] = {}
    for fb in sorted(feedbacks, key=lambda row: row.created_at):
        latest[fb.evidence_id] = fb

    kept: list[EvidenceItem] = []
    removed: list[EvidenceItem] = []
    summary = FeedbackApplySummary()

    for item in items:
        fb = latest.get(item.id)
        if fb is None:
            kept.append(item)
            continue

        summary.applied += 1
        summary.evidence_ids.append(item.id)

        if fb.label == "irrelevant":
            summary.irrelevant += 1
            removed.append(
                item.model_copy(
                    update={
                        "provenance_status": "rejected",
                        "provenance_reason": "scientist_feedback_irrelevant",
                    }
                )
            )
            continue

        updates: dict = {}
        if fb.label == "wrong_direction":
            summary.wrong_direction += 1
            if item.direction == "inhibit":
                updates["direction"] = "activate"
            elif item.direction == "activate":
                updates["direction"] = "inhibit"
            else:
                updates["direction"] = "unresolved"
            # Keep stance; direction correction is the main learning signal.
        elif fb.label == "important":
            summary.important += 1
            updates["directness"] = min(1.0, float(item.directness) + 0.18)
            if item.quality == EvidenceQuality.LOW:
                updates["quality"] = EvidenceQuality.MODERATE
            elif item.quality == EvidenceQuality.MODERATE:
                updates["quality"] = EvidenceQuality.HIGH

        kept.append(item.model_copy(update=updates) if updates else item)

    return kept, removed, summary
