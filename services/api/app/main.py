from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Load local .env before reading LLM/Mongo settings.
_here = Path(__file__).resolve()
for _idx in (3, 2, 1):
    if _idx < len(_here.parents):
        _candidate = _here.parents[_idx] / ".env"
        if _candidate.is_file():
            load_dotenv(_candidate)
            break
else:
    load_dotenv(Path.cwd() / ".env")

from .auth import AuthUser, OptionalUser, auth_configured
from .cache import close_redis, connect_redis, redis_status
from .chat import ChatRequest, ChatResponse, chat_completion, chat_history, chat_sessions, remove_chat_session
from .db import close_mongo, connect_mongo, mongo_status
from .feedback_models import FeedbackCreate
from .feedback_store import list_feedback, save_feedback
from .models import AnalysisRequest, RunResponse
from .orchestrator import orchestrate_run
from .reasoning import OpenAICompatibleProvider
from .repository import analytics_summary, get_run, list_runs, save_run
from .scoring import QUALITY_MULTIPLIER, WEIGHTS

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "")
    extras = [origin.strip() for origin in configured.split(",") if origin.strip() and origin.strip() != "*"]
    return DEFAULT_ORIGINS + extras


def _cors_origin_regex() -> str | None:
    configured = os.getenv("CORS_ORIGINS", "")
    parts = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if "*" in parts:
        return r"https?://.*"
    return r"https://[a-zA-Z0-9-]+\.vercel\.app"


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await connect_mongo()
    except Exception:
        # API stays up even if Mongo is misconfigured; health reports the error.
        pass
    connect_redis()
    yield
    close_redis()
    await close_mongo()


app = FastAPI(
    title="BioLead Evidence API",
    version="1.1.0",
    description="Auditable causal-gene prioritization for dermatology research.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def analyze(request: AnalysisRequest, user: AuthUser | None = None) -> RunResponse:
    run_id, results = await orchestrate_run(request)
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
        "redis": redis_status(),
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


@app.post("/api/feedback")
async def create_feedback(payload: FeedbackCreate, user: OptionalUser) -> dict:
    record = await save_feedback(
        payload,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    return {"ok": True, "feedback": record.model_dump(mode="json")}


@app.get("/api/feedback")
async def get_feedback(
    user: OptionalUser,
    disease: str = Query(min_length=2),
    gene: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    rows = await list_feedback(disease=disease, gene=gene, limit=limit)
    return {
        "enabled": True,
        "disease": disease,
        "gene": gene.upper(),
        "count": len(rows),
        "feedback": [row.model_dump(mode="json") for row in rows],
    }


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


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: OptionalUser) -> ChatResponse:
    return await chat_completion(
        request,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )


@app.get("/api/chat/sessions")
async def chat_sessions_endpoint(user: OptionalUser) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to view Clara history")
    sessions, persisted = await chat_sessions(user_id=user.id)
    return {"signed_in": True, "persisted": persisted, "sessions": sessions}


@app.get("/api/chat/history")
async def chat_history_endpoint(
    user: OptionalUser,
    run_id: str | None = Query(default=None, max_length=200),
    chat_id: str | None = Query(default=None, max_length=200),
) -> dict:
    cid = (chat_id or run_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="chat_id is required")
    messages, persisted = await chat_history(
        chat_id=cid,
        run_id=run_id,
        user_id=user.id if user else None,
    )
    return {
        "chat_id": cid,
        "run_id": run_id,
        "signed_in": user is not None,
        "persisted": persisted,
        "messages": messages,
    }


@app.delete("/api/chat/sessions/{chat_id}")
async def chat_delete_endpoint(chat_id: str, user: OptionalUser) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to delete Clara history")
    deleted = await remove_chat_session(user_id=user.id, chat_id=chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"deleted": True, "chat_id": chat_id}


@app.get("/api/analyze/stream")
async def analyze_stream(
    user: OptionalUser,
    disease: str = Query(default="Atopic dermatitis"),
    genes: str = Query(default="IL4R,FLG,S100A8"),
    tissue: str = Query(default="skin"),
    mode: str = Query(default="demo", pattern="^(demo|live)$"),
    refresh: bool = Query(default=False),
) -> StreamingResponse:
    request = AnalysisRequest(
        disease=disease,
        genes=[gene.strip() for gene in genes.split(",") if gene.strip()][:5],
        tissue=tissue,
        mode=mode,  # type: ignore[arg-type]
        refresh=refresh,
    )

    async def events():
        stages = [
            ("retrieve", "Retrieving genetics, literature, and clinical sources"),
            ("extract", "Normalizing evidence and applying provenance gate"),
            ("score", "Applying deterministic evidence rubric"),
            ("falsify", "Searching counter-hypotheses and classifying conflicts"),
            ("decide", "Merging votes into a versioned decision snapshot"),
        ]
        for stage, message in stages:
            yield f"event: progress\ndata: {json.dumps({'stage': stage, 'message': message})}\n\n"
            await asyncio.sleep(0.2)
        result = await analyze(request, user=user)
        yield "event: result\ndata: " + result.model_dump_json() + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
