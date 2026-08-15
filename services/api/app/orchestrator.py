from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

from .fixtures import get_demo_evidence
from .feedback_store import list_feedback
from .models import AnalysisRequest, AnalysisResult, PipelineTrace, StageTrace
from .provenance import apply_provenance_gate
from .rag import RagTrace, retrieve_rag
from .reasoning import NarrativeProvider, OpenAICompatibleProvider, build_result


def _retry_attempts() -> int:
    raw = os.getenv("ORCHESTRATOR_RETRIES", "2").strip()
    return max(1, min(4, int(raw))) if raw.isdigit() else 2


def _ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


async def _retrieve_live(
    disease: str,
    gene: str,
    tissue: str,
    *,
    refresh: bool = False,
) -> tuple[list, list[str], int, RagTrace]:
    """Hybrid RAG retrieve with bounded retries on total source failure."""
    attempts = _retry_attempts()
    errors: list[str] = []
    items: list = []
    used = 0
    trace = RagTrace(refreshed=refresh, cache_mode="fresh" if refresh else "shared")
    for attempt in range(attempts):
        used = attempt + 1
        # Only force cache bypass on first attempt when refresh requested.
        result = await retrieve_rag(
            disease,
            gene,
            tissue,
            refresh=refresh and attempt == 0,
        )
        items, errors, trace = result.items, result.errors, result.trace
        if items or not errors or attempt == attempts - 1:
            break
        await asyncio.sleep(0.35 * (attempt + 1))
    return items, errors, used, trace


async def orchestrate_gene(
    request: AnalysisRequest,
    gene: str,
    *,
    run_id: str,
    provider: NarrativeProvider | None = None,
) -> AnalysisResult:
    """
    Product orchestrator:
    Retrieve (RAG) → Extract (provenance) → Score → Falsify → Decide
    with retries and thin-evidence abstention.
    """
    stages: list[StageTrace] = []
    provider = provider or OpenAICompatibleProvider()
    retries_used = 0
    source_errors: list[str] = []
    rag_trace = RagTrace()

    # 1) Retrieve
    t0 = time.perf_counter()
    if request.mode == "demo":
        evidence = get_demo_evidence(request.disease, gene)
        if evidence:
            retrieve_status = "ok"
            retrieve_detail = f"Loaded curated demo evidence ({len(evidence)} items)."
        else:
            retrieve_status = "skipped"
            retrieve_detail = (
                f"No curated demo pack for {request.disease} × {gene}; "
                "abstaining rather than inventing papers."
            )
        stages.append(
            StageTrace(
                id="retrieve",
                label="Retrieve",
                status=retrieve_status,  # type: ignore[arg-type]
                detail=retrieve_detail,
                duration_ms=_ms(t0),
            )
        )
    else:
        evidence, source_errors, retries_used, rag_trace = await _retrieve_live(
            request.disease,
            gene,
            request.tissue,
            refresh=bool(request.refresh),
        )
        if evidence and not source_errors:
            status = "ok"
            detail = (
                f"RAG retrieved {len(evidence)} items "
                f"({rag_trace.structured_kept} structured / {rag_trace.literature_kept} literature)."
            )
        elif evidence and source_errors:
            status = "degraded"
            detail = (
                f"RAG retrieved {len(evidence)} items with partial source failures "
                f"({', '.join(source_errors)})."
            )
        elif source_errors:
            status = "failed"
            detail = f"All live sources failed after {retries_used} attempt(s): {', '.join(source_errors)}."
        else:
            status = "degraded"
            detail = "RAG retrieval returned no normalized evidence items."
        if rag_trace.refreshed:
            detail += " Cache refresh requested."
        if retries_used > 1:
            detail += f" Retries used: {retries_used - 1}."
        stages.append(
            StageTrace(
                id="retrieve",
                label="Retrieve",
                status=status,  # type: ignore[arg-type]
                detail=detail,
                duration_ms=_ms(t0),
            )
        )

    # 2) Extract / provenance
    t1 = time.perf_counter()
    accepted, rejected = apply_provenance_gate(evidence)
    thin = len(accepted) == 0
    if thin:
        extract_status = "failed" if evidence else "skipped"
        extract_detail = (
            f"Provenance rejected all {len(rejected)} item(s); abstaining."
            if rejected
            else "No evidence available to extract; abstaining."
        )
    else:
        extract_status = "ok" if not rejected else "degraded"
        extract_detail = (
            f"Accepted {len(accepted)} item(s)"
            + (f"; rejected {len(rejected)}." if rejected else ".")
        )
    stages.append(
        StageTrace(
            id="extract",
            label="Extract",
            status=extract_status,  # type: ignore[arg-type]
            detail=extract_detail,
            duration_ms=_ms(t1),
        )
    )

    # 3–5) Score → Falsify → Decide
    t2 = time.perf_counter()
    # The presentation/demo corpus is immutable by design. Scientist feedback is
    # intentionally applied only to Live runs so a prior review cannot silently
    # change a frozen golden verdict or snapshot.
    feedbacks = (
        await list_feedback(disease=request.disease, gene=gene)
        if request.mode == "live"
        else []
    )
    result = await build_result(
        request.disease,
        gene,
        request.tissue,
        evidence,
        provider=provider,
        run_id=run_id,
        source_errors=source_errors,
        mode=request.mode,
        feedbacks=feedbacks,
    )
    decide_ms = _ms(t2)

    scorecard = result.scorecard
    stages.append(
        StageTrace(
            id="score",
            label="Score",
            status="ok" if not thin else "skipped",
            detail=(
                f"Causality {scorecard.causality.value}, actionability {scorecard.actionability.value}, "
                f"quality {scorecard.evidence_quality.value}, pillars {scorecard.independent_pillars}."
            ),
            duration_ms=max(1, decide_ms // 3),
        )
    )

    falsify = result.decision_ledger.falsification if result.decision_ledger else None
    stages.append(
        StageTrace(
            id="falsify",
            label="Falsify",
            status="ok" if falsify and falsify.gate_completed else "failed",
            detail=(
                f"Gate {falsify.status}; hard unresolved="
                f"{result.decision_ledger.hard_contradictions_unresolved if result.decision_ledger else 0}."
                if falsify
                else "Falsification gate missing."
            ),
            duration_ms=max(1, decide_ms // 3),
        )
    )
    stages.append(
        StageTrace(
            id="decide",
            label="Decide",
            status="ok",
            detail=f"Verdict={result.verdict}; snapshot={result.decision_ledger.snapshot_id if result.decision_ledger else 'n/a'}.",
            duration_ms=max(1, decide_ms // 3),
        )
    )

    fb = result.feedback_summary
    pipeline = PipelineTrace(
        stages=stages,
        retries=max(0, retries_used - 1),
        source_errors=source_errors,
        thin_evidence=thin,
        mode=request.mode,
        rag_queries=rag_trace.queries,
        rag_sources_hit=rag_trace.sources_hit,
        rag_sources_failed=rag_trace.sources_failed,
        rag_cache_mode=rag_trace.cache_mode,
        rag_refreshed=rag_trace.refreshed,
        rag_literature_kept=rag_trace.literature_kept,
        rag_structured_kept=rag_trace.structured_kept,
        feedback_applied=fb.applied if fb else 0,
        feedback_irrelevant=fb.irrelevant if fb else 0,
        feedback_wrong_direction=fb.wrong_direction if fb else 0,
        feedback_important=fb.important if fb else 0,
    )
    limitations = list(result.limitations)
    if thin:
        limitations.append("Orchestrator marked thin evidence and forced an abstention-safe path.")
    if retries_used > 1:
        limitations.append(f"Orchestrator retried live retrieval ({retries_used} attempts).")
    if request.mode == "live":
        limitations.append(
            "Live RAG used structured sources plus multi-query literature retrieval with lexical reranking."
        )
    if rag_trace.refreshed:
        limitations.append("Evidence cache was bypassed for this run (refresh=true).")
    if fb and fb.applied:
        limitations.append("Prior scientist feedback influenced ranking/direction for this gene.")

    return result.model_copy(update={"pipeline": pipeline, "limitations": limitations})


async def orchestrate_run(
    request: AnalysisRequest,
    *,
    provider: NarrativeProvider | None = None,
) -> tuple[str, list[AnalysisResult]]:
    run_id = str(uuid4())
    provider = provider or OpenAICompatibleProvider()
    results: list[AnalysisResult] = []
    for gene in request.genes:
        results.append(
            await orchestrate_gene(request, gene, run_id=run_id, provider=provider)
        )
    return run_id, results
