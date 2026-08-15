import asyncio

from app.feedback_models import FeedbackCreate
from app.feedback_store import clear_memory_feedback, save_feedback
from app.models import AnalysisRequest
from app.orchestrator import orchestrate_gene, orchestrate_run


def test_orchestrator_demo_pipeline_stages():
    async def _run():
        request = AnalysisRequest(
            disease="Atopic dermatitis",
            genes=["IL4R"],
            tissue="skin",
            mode="demo",
        )
        result = await orchestrate_gene(request, "IL4R", run_id="run-test")
        assert result.pipeline is not None
        assert [s.id for s in result.pipeline.stages] == [
            "retrieve",
            "extract",
            "score",
            "falsify",
            "decide",
        ]
        assert result.pipeline.mode == "demo"
        assert result.pipeline.thin_evidence is False
        assert result.decision_ledger is not None
        assert result.pipeline.stages[0].status == "ok"
        assert result.pipeline.stages[-1].status == "ok"
        assert result.verdict == "Driver"

    asyncio.run(_run())


def test_orchestrator_run_multi_gene():
    async def _run():
        request = AnalysisRequest(
            disease="Atopic dermatitis",
            genes=["IL4R", "FLG", "S100A8"],
            mode="demo",
        )
        run_id, results = await orchestrate_run(request)
        assert run_id
        assert len(results) == 3
        assert all(r.pipeline is not None for r in results)
        assert {r.gene for r in results} == {"IL4R", "FLG", "S100A8"}

    asyncio.run(_run())


def test_demo_ignores_persisted_feedback_to_keep_snapshot_frozen(monkeypatch):
    async def _run():
        clear_memory_feedback()
        monkeypatch.setattr("app.feedback_store.get_db", lambda: None)
        await save_feedback(
            FeedbackCreate(
                disease="Atopic dermatitis",
                gene="IL4R",
                evidence_id="il4r-clinical",
                label="irrelevant",
            )
        )
        request = AnalysisRequest(
            disease="Atopic dermatitis",
            genes=["IL4R"],
            tissue="skin",
            mode="demo",
        )
        result = await orchestrate_gene(request, "IL4R", run_id="run-frozen")
        assert result.verdict == "Driver"
        assert result.pipeline is not None
        assert result.pipeline.feedback_applied == 0
        assert result.decision_ledger is not None
        assert result.decision_ledger.snapshot_id == "BL-IL4R-AtopicDerm-0ac22b62a703"
        clear_memory_feedback()

    asyncio.run(_run())


def test_demo_skips_llm_voters_even_when_ensemble_is_required(monkeypatch):
    class ExplodingProvider:
        enabled = True

        async def vote(self, *_args, **_kwargs):
            raise AssertionError("Demo must not call an LLM provider")

    async def _run():
        monkeypatch.setenv("ENSEMBLE_REQUIRED", "true")
        request = AnalysisRequest(
            disease="Atopic dermatitis",
            genes=["IL4R"],
            tissue="skin",
            mode="demo",
        )
        result = await orchestrate_gene(
            request,
            "IL4R",
            run_id="run-no-llm",
            provider=ExplodingProvider(),
        )
        assert result.verdict == "Driver"
        assert result.ensemble is not None
        assert result.ensemble.policy == "deterministic_only"
        assert any("frozen deterministic decision path" in item for item in result.limitations)

    asyncio.run(_run())
