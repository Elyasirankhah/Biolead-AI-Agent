from __future__ import annotations

from collections import defaultdict

from .models import DimensionScore, EvidenceItem, EvidenceQuality, EvidenceType, ScoreCard

WEIGHTS = {
    EvidenceType.MENDELIAN_RANDOMIZATION: 30,
    EvidenceType.COLOCALIZATION: 26,
    EvidenceType.HUMAN_GENETICS: 22,
    EvidenceType.CAUSAL_PERTURBATION: 22,
    EvidenceType.CLINICAL_PHARMACOLOGY: 20,
    EvidenceType.MECHANISTIC_COHERENCE: 12,
    EvidenceType.DIFFERENTIAL_EXPRESSION: 6,
    EvidenceType.LITERATURE: 4,
}

QUALITY_MULTIPLIER = {
    EvidenceQuality.HIGH: 1.0,
    EvidenceQuality.MODERATE: 0.7,
    EvidenceQuality.LOW: 0.4,
}

CAUSAL_CATEGORIES = {
    EvidenceType.MENDELIAN_RANDOMIZATION,
    EvidenceType.COLOCALIZATION,
    EvidenceType.HUMAN_GENETICS,
    EvidenceType.CAUSAL_PERTURBATION,
    EvidenceType.CLINICAL_PHARMACOLOGY,
    EvidenceType.MECHANISTIC_COHERENCE,
}


def _item_strength(item: EvidenceItem) -> float:
    tissue_factor = 1.0 if item.tissue_relevant else 0.55
    return QUALITY_MULTIPLIER[item.quality] * item.directness * tissue_factor


def score_evidence(items: list[EvidenceItem]) -> tuple[ScoreCard, str, int]:
    by_category: dict[EvidenceType, list[EvidenceItem]] = defaultdict(list)
    for item in items:
        by_category[item.category].append(item)

    category_scores: dict[EvidenceType, float] = {}
    contradiction = 0.0
    independent_keys: set[str] = set()

    for category, category_items in by_category.items():
        supports = [item for item in category_items if item.stance == "supports"]
        contradicts = [item for item in category_items if item.stance == "contradicts"]
        # Diminishing returns prevent paper volume from masquerading as independent proof.
        support_strengths = sorted((_item_strength(item) for item in supports), reverse=True)
        support = sum(value * (0.55**index) for index, value in enumerate(support_strengths))
        support = min(1.0, support)
        category_scores[category] = WEIGHTS[category] * support

        for item in supports:
            independent_keys.add(item.independent_key)
        contradiction += sum(WEIGHTS[category] * _item_strength(item) * 0.7 for item in contradicts)

    causal_raw = sum(category_scores.get(category, 0) for category in CAUSAL_CATEGORIES)
    causal_max = sum(WEIGHTS[category] for category in CAUSAL_CATEGORIES)
    causality = round(max(0, min(100, (causal_raw / causal_max) * 100 - contradiction)))

    action_raw = (
        category_scores.get(EvidenceType.CLINICAL_PHARMACOLOGY, 0) * 1.5
        + category_scores.get(EvidenceType.CAUSAL_PERTURBATION, 0)
        + category_scores.get(EvidenceType.MECHANISTIC_COHERENCE, 0) * 0.5
    )
    actionability = round(max(0, min(100, action_raw / 0.46 - contradiction * 0.5)))

    if items:
        quality = round(
            100
            * sum(QUALITY_MULTIPLIER[item.quality] * item.directness for item in items)
            / len(items)
        )
    else:
        quality = 0

    causal_pillars = sum(
        1
        for category in CAUSAL_CATEGORIES
        if category_scores.get(category, 0) >= WEIGHTS[category] * 0.45
    )
    correlational = category_scores.get(EvidenceType.DIFFERENTIAL_EXPRESSION, 0) + category_scores.get(
        EvidenceType.LITERATURE, 0
    )

    has_causal_counterevidence = any(
        item.stance == "contradicts" and item.category in CAUSAL_CATEGORIES for item in items
    )

    if (
        quality >= 45
        and correlational >= 5
        and causality < 32
        and has_causal_counterevidence
    ):
        verdict = "Passenger"
    elif quality < 35 or causal_pillars < 2:
        verdict = "Insufficient evidence"
    elif causality >= 58 and causal_pillars >= 2:
        verdict = "Driver"
    else:
        verdict = "Insufficient evidence"

    confidence = round(
        min(
            95,
            max(
                20,
                quality * 0.45
                + min(causal_pillars, 4) * 9
                + min(len(independent_keys), 6) * 3
                - contradiction * 0.5,
            ),
        )
    )
    if verdict == "Insufficient evidence":
        confidence = min(confidence, 69)

    scorecard = ScoreCard(
        causality=DimensionScore(
            value=causality,
            rationale="Weighted causal evidence after contradiction penalties.",
        ),
        actionability=DimensionScore(
            value=actionability,
            rationale="Perturbational and clinical evidence for a tractable intervention.",
        ),
        evidence_quality=DimensionScore(
            value=quality,
            rationale="Directness, source quality, and tissue relevance across evidence items.",
        ),
        contradiction_penalty=round(min(100, contradiction)),
        independent_pillars=causal_pillars,
        evidence_count=len(items),
    )
    return scorecard, verdict, confidence
