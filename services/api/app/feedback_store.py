from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .db import get_db
from .feedback_models import FeedbackCreate, FeedbackRecord

# Offline/demo fallback when Mongo is not configured.
_MEMORY_FEEDBACK: list[dict[str, Any]] = []


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    payload = dict(doc)
    payload.pop("_id", None)
    return payload


def _norm_disease(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _norm_gene(value: str) -> str:
    return value.strip().upper()


async def ensure_feedback_indexes() -> None:
    db = get_db()
    if db is None:
        return
    await db.feedback.create_index([("disease_norm", 1), ("gene", 1), ("evidence_id", 1), ("created_at", -1)])
    await db.feedback.create_index("feedback_id", unique=True)


async def save_feedback(
    payload: FeedbackCreate,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
) -> FeedbackRecord:
    record = FeedbackRecord(
        feedback_id=str(uuid4()),
        disease=payload.disease.strip(),
        gene=_norm_gene(payload.gene),
        evidence_id=payload.evidence_id.strip(),
        label=payload.label,
        note=(payload.note or None),
        run_id=payload.run_id,
        user_id=user_id,
        user_email=user_email,
        created_at=datetime.now(timezone.utc),
    )
    document = {
        **record.model_dump(mode="json"),
        "disease_norm": _norm_disease(record.disease),
    }
    db = get_db()
    if db is None:
        # Replace prior memory feedback for same evidence key.
        key = (document["disease_norm"], document["gene"], document["evidence_id"])
        _MEMORY_FEEDBACK[:] = [
            row
            for row in _MEMORY_FEEDBACK
            if (row.get("disease_norm"), row.get("gene"), row.get("evidence_id")) != key
        ]
        _MEMORY_FEEDBACK.append(document)
        return record

    await db.feedback.update_one(
        {
            "disease_norm": document["disease_norm"],
            "gene": document["gene"],
            "evidence_id": document["evidence_id"],
        },
        {"$set": document},
        upsert=True,
    )
    return record


async def list_feedback(
    *,
    disease: str,
    gene: str,
    limit: int = 100,
) -> list[FeedbackRecord]:
    disease_norm = _norm_disease(disease)
    gene_norm = _norm_gene(gene)
    limit = max(1, min(limit, 200))
    db = get_db()
    rows: list[dict[str, Any]]
    if db is None:
        rows = [
            row
            for row in _MEMORY_FEEDBACK
            if row.get("disease_norm") == disease_norm and row.get("gene") == gene_norm
        ]
        rows = sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)[:limit]
    else:
        cursor = (
            db.feedback.find({"disease_norm": disease_norm, "gene": gene_norm})
            .sort("created_at", -1)
            .limit(limit)
        )
        rows = [_serialize(doc) async for doc in cursor]

    out: list[FeedbackRecord] = []
    for row in rows:
        try:
            out.append(FeedbackRecord.model_validate(row))
        except Exception:
            continue
    return out


def clear_memory_feedback() -> None:
    """Test helper."""
    _MEMORY_FEEDBACK.clear()
