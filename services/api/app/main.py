from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

_here = Path(__file__).resolve()
for _idx in (3, 2, 1):
    if _idx < len(_here.parents):
        _candidate = _here.parents[_idx] / ".env"
        if _candidate.is_file():
            load_dotenv(_candidate)
            break
else:
    load_dotenv(Path.cwd() / ".env")

from .adapters import collect_live_evidence
from .auth import AuthUser, OptionalUser, auth_configured
from .db import close_mongo, connect_mongo, mongo_status
from .fixtures import get_demo_evidence
from .models import AnalysisRequest, RunResponse
from .reasoning import OpenAICompatibleProvider, build_result
from .repository import analytics_summary, get_run, list_runs, save_run
from .scoring import QUALITY_MULTIPLIER, WEIGHTS

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "")
    extras = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return DEFAULT_ORIGINS + extras


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await connect_mongo()
    except Exception:
        # API stays up even if Mongo is misconfigured; health reports the error.
        pass
    yield
    await close_mongo()


app = FastAPI(
    title="BioLead Evidence API",
    version="1.0.0",
    description="Auditable causal-gene prioritization for dermatology research.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://[a-zA-Z0-9-]+\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def analyze(request: AnalysisRequest, user: AuthUser | None = None) -> RunResponse:
    run_id = str(uuid4())
    provider = OpenAICompatibleProvider()
    results = []
    for gene in request.genes:
        errors: list[str] = []
        if request.mode == "demo":
            evidence = get_demo_evidence(request.disease, gene)
        else:
            evidence, errors = await collect_live_evidence(request.disease, gene, request.tissue)
        results.append(
            await build_result(
                request.disease,
                gene,
                request.tissue,
                evidence,
                provider=provider,
                run_id=run_id,
                source_errors=errors,
            )
        )
    response = RunResponse(run_id=run_id, disease=request.disease, results=results)
    await save_run(
        request,
        response,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    return response


@app.get("/health")
async def health() -> dict:
    provider = OpenAICompatibleProvider()
    return {
        "status": "ok",
        "service": "biolead-api",
        "version": app.version,
        "mongodb": await mongo_status(),
        "auth": {
            "supabase_configured": auth_configured(),
            "required": os.getenv("AUTH_REQUIRED", "false").strip().lower() in {"1", "true", "yes"},
        },
        "llm": {
            "enabled": provider.enabled,
            "model": provider.model if provider.enabled else None,
            "ensemble": "deterministic+advocate+falsifier",
            "ensemble_required": os.getenv("ENSEMBLE_REQUIRED", "true").strip().lower()
            in {"1", "true", "yes"},
        },
    }


@app.get("/api/rubric")
async def rubric() -> dict:
    return {
        "weights": {key.value: value for key, value in WEIGHTS.items()},
        "quality_multipliers": {key.value: value for key, value in QUALITY_MULTIPLIER.items()},
        "causal_chain": [
            {"edge": "Variant → Gene", "pillars": ["mendelian_randomization", "colocalization", "human_genetics"]},
            {"edge": "Gene → Disease", "pillars": ["human_genetics", "causal_perturbation"]},
            {"edge": "Gene → Clinical rescue", "pillars": ["clinical_pharmacology", "causal_perturbation"]},
            {"edge": "Mechanism", "pillars": ["mechanistic_coherence"]},
        ],
        "policy": {
            "driver": "causality >= 58, quality >= 35, and at least two independent causal pillars",
            "passenger": "correlative signal plus explicit causal counter-evidence and causality < 32",
            "abstain": "all other cases return Insufficient evidence",
        },
        "version": "1.1.0",
    }


@app.post("/api/analyze", response_model=RunResponse)
async def analyze_endpoint(request: AnalysisRequest, user: OptionalUser) -> RunResponse:
    return await analyze(request, user=user)


@app.get("/api/demo", response_model=RunResponse)
async def demo(user: OptionalUser) -> RunResponse:
    return await analyze(
        AnalysisRequest(
            disease="Atopic dermatitis",
            genes=["IL4R", "FLG", "S100A8"],
            tissue="skin",
            mode="demo",
        ),
        user=user,
    )


@app.get("/api/runs")
async def runs(
    user: OptionalUser,
    limit: int = Query(default=20, ge=1, le=100),
    mine: bool = Query(default=False),
) -> dict:
    status = await mongo_status()
    if not status.get("enabled"):
        return {"enabled": False, "runs": [], "detail": "MongoDB not configured"}
    if status.get("status") != "ok":
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {status.get('detail')}")
    user_id = user.id if mine and user else None
    return {"enabled": True, "runs": await list_runs(limit=limit, user_id=user_id)}


@app.get("/api/runs/{run_id}")
async def run_detail(run_id: str, user: OptionalUser) -> dict:
    status = await mongo_status()
    if not status.get("enabled"):
        raise HTTPException(status_code=503, detail="MongoDB not configured")
    if status.get("status") != "ok":
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {status.get('detail')}")
    doc = await get_run(run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return doc


@app.get("/api/analytics")
async def analytics(user: OptionalUser, mine: bool = Query(default=False)) -> dict:
    status = await mongo_status()
    if not status.get("enabled"):
        return {"enabled": False, "detail": "MongoDB not configured"}
    if status.get("status") != "ok":
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {status.get('detail')}")
    user_id = user.id if mine and user else None
    if mine and not user:
        raise HTTPException(status_code=401, detail="Sign in to view your analytics")
    return await analytics_summary(user_id=user_id)


@app.get("/api/analyze/stream")
async def analyze_stream(
    user: OptionalUser,
    disease: str = Query(default="Atopic dermatitis"),
    genes: str = Query(default="IL4R,FLG,S100A8"),
    tissue: str = Query(default="skin"),
    mode: str = Query(default="demo", pattern="^(demo|live)$"),
) -> StreamingResponse:
    request = AnalysisRequest(
        disease=disease,
        genes=[gene.strip() for gene in genes.split(",") if gene.strip()][:5],
        tissue=tissue,
        mode=mode,
    )

    async def events():
        stages = [
            ("normalize", "Resolving gene and disease identifiers"),
            ("collect", "Collecting genetics, perturbation, clinical, and literature evidence"),
            ("score", "Applying deterministic evidence rubric"),
            ("critic", "Falsifying the leading hypothesis"),
        ]
        for stage, message in stages:
            yield f"event: progress\ndata: {json.dumps({'stage': stage, 'message': message})}\n\n"
            await asyncio.sleep(0.25)
        result = await analyze(request, user=user)
        yield "event: result\ndata: " + result.model_dump_json() + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
