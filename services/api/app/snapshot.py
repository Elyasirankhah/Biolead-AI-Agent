from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import EvidenceItem

# Bump when decision-critical logic changes.
SCORING_VERSION = "1.1.0"
PROVENANCE_VERSION = "1.0.0"
FALSIFICATION_VERSION = "1.0.0"
ENSEMBLE_POLICY_VERSION = "1.0.0"
RULES_VERSION = f"score:{SCORING_VERSION}|prov:{PROVENANCE_VERSION}|falsify:{FALSIFICATION_VERSION}|ensemble:{ENSEMBLE_POLICY_VERSION}"


def _norm(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def normalize_evidence_for_snapshot(items: list[EvidenceItem]) -> list[dict[str, Any]]:
    """Stable, order-independent evidence payload for hashing."""
    rows: list[dict[str, Any]] = []
    for item in items:
        if item.provenance_status == "rejected":
            continue
        rows.append(
            {
                "id": item.id,
                "category": item.category.value,
                "title": _norm(item.title),
                "summary": _norm(item.summary[:240]),
                "stance": item.stance,
                "direction": item.direction,
                "quality": item.quality.value,
                "directness": round(float(item.directness), 4),
                "tissue_relevant": bool(item.tissue_relevant),
                "independent_key": item.independent_key,
                "source_url": str(item.source_url),
                "citation": _norm(item.citation),
            }
        )
    rows.sort(key=lambda row: (row["independent_key"], row["id"], row["title"]))
    return rows


def build_decision_snapshot(
    *,
    gene: str,
    disease: str,
    tissue: str,
    direction: str,
    verdict: str,
    accepted_items: list[EvidenceItem],
    mode: str | None = None,
) -> dict[str, Any]:
    """
    Deterministic decision snapshot.
    Same normalized evidence + rules version => same content_hash / snapshot_id.
    """
    payload = {
        "gene": gene.upper().strip(),
        "disease": _norm(disease),
        "tissue": _norm(tissue),
        "direction": direction,
        "verdict": verdict,
        "rules_version": RULES_VERSION,
        "evidence": normalize_evidence_for_snapshot(accepted_items),
        "mode": (mode or "").strip().lower() or None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    short = content_hash[:12]
    disease_slug = "".join(ch for ch in disease.title() if ch.isalnum())[:10] or "Disease"
    snapshot_id = f"BL-{gene.upper()}-{disease_slug}-{short}"
    return {
        "snapshot_id": snapshot_id,
        "content_hash": content_hash,
        "rules_version": RULES_VERSION,
        "scoring_version": SCORING_VERSION,
        "provenance_version": PROVENANCE_VERSION,
        "falsification_version": FALSIFICATION_VERSION,
        "ensemble_policy_version": ENSEMBLE_POLICY_VERSION,
        "reproducible": True,
        "canonical_bytes": len(canonical),
    }
