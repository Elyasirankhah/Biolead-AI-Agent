from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import get_db
from .models import AnalysisRequest, RunResponse


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    payload = dict(doc)
    payload.pop("_id", None)
    return payload


async def save_run(
    request: AnalysisRequest,
    response: RunResponse,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
) -> bool:
    """Persist an analysis run. Returns False if Mongo is unavailable."""
    db = get_db()
    if db is None:
        return False
    document = {
        "run_id": response.run_id,
        "disease": response.disease,
        "tissue": request.tissue,
        "mode": request.mode,
        "genes": request.genes,
        "intervention_direction": request.intervention_direction,
        "created_at": datetime.now(timezone.utc),
        "result_count": len(response.results),
        "verdicts": {item.gene: item.verdict for item in response.results},
        "results": [item.model_dump(mode="json") for item in response.results],
        "user_id": user_id,
        "user_email": user_email,
    }
    await db.runs.update_one({"run_id": response.run_id}, {"$set": document}, upsert=True)
    return True


async def get_run(run_id: str) -> dict[str, Any] | None:
    db = get_db()
    if db is None:
        return None
    doc = await db.runs.find_one({"run_id": run_id})
    return _serialize(doc) if doc else None


async def list_runs(limit: int = 20, user_id: str | None = None) -> list[dict[str, Any]]:
    db = get_db()
    if db is None:
        return []
    limit = max(1, min(limit, 100))
    query: dict[str, Any] = {}
    if user_id:
        query["user_id"] = user_id
    cursor = db.runs.find(
        query,
        {
            "run_id": 1,
            "disease": 1,
            "mode": 1,
            "genes": 1,
            "created_at": 1,
            "verdicts": 1,
            "result_count": 1,
            "user_id": 1,
            "user_email": 1,
        },
    ).sort("created_at", -1).limit(limit)
    return [_serialize(doc) async for doc in cursor]


async def analytics_summary(user_id: str | None = None) -> dict[str, Any]:
    db = get_db()
    if db is None:
        return {"enabled": False}
    match: dict[str, Any] = {}
    if user_id:
        match["user_id"] = user_id

    total = await db.runs.count_documents(match)
    users = await db.runs.distinct("user_id", {**match, "user_id": {"$ne": None}})
    pipeline: list[dict[str, Any]] = []
    if match:
        pipeline.append({"$match": match})
    pipeline.extend(
        [
            {"$project": {"verdict_pairs": {"$objectToArray": "$verdicts"}}},
            {"$unwind": "$verdict_pairs"},
            {"$group": {"_id": "$verdict_pairs.v", "count": {"$sum": 1}}},
        ]
    )
    verdict_rows = await db.runs.aggregate(pipeline).to_list(20)
    gene_pipeline: list[dict[str, Any]] = []
    if match:
        gene_pipeline.append({"$match": match})
    gene_pipeline.extend(
        [
            {"$unwind": "$genes"},
            {"$group": {"_id": "$genes", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ]
    )
    gene_rows = await db.runs.aggregate(gene_pipeline).to_list(8)
    return {
        "enabled": True,
        "scope": "user" if user_id else "global",
        "total_runs": total,
        "unique_users": len([user for user in users if user]),
        "verdict_counts": {row["_id"]: row["count"] for row in verdict_rows},
        "top_genes": [{"gene": row["_id"], "runs": row["count"]} for row in gene_rows],
    }
