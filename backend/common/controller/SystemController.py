import json

from fastapi import APIRouter, Depends, Response

from common.JWTDecode import get_admin_owner


class SystemController:
    def __init__(self, context):
        self.context = context
        self.router = APIRouter(tags=["system"])
        self.router.add_api_route("/health", self.health, methods=["GET"])
        self.router.add_api_route("/ready", self.ready, methods=["GET"])
        self.router.add_api_route("/status", self.status, methods=["GET"])
        self.router.add_api_route("/evaluation", self.evaluation, methods=["GET"])
        self.router.add_api_route("/metrics", self.metrics, methods=["GET"])

    def health(self):
        # Liveness: the process is up. It deliberately does NOT claim models/corpus are ready.
        return {"status": "ok", "version": "1.0.0"}

    def ready(self, owner=Depends(get_admin_owner)):
        # Readiness: only true when models, corpus and core persistence are actually usable.
        ctx = self.context
        ready = bool(ctx.corpus)
        checks = {
            "corpus": ready,
            "dense_loaded": bool(ctx.retriever.dense),
            "reranker_loaded": bool(ctx.agent.reranker.reranker),
            "redis": ctx.memory_service.redis_status in {"connected", "disabled"},
            "neo4j": ctx.neo4j.status,
            "database": ctx.settings.database_backend,
        }
        all_ready = ready and checks["dense_loaded"]
        return {
            "ready": all_ready,
            "checks": checks,
            "version": "1.0.0",
        }

    def status(self, owner=Depends(get_admin_owner)):
        ctx = self.context
        settings = ctx.settings
        return {
            "version": "1.0.0",
            "corpus": ctx.corpus.manifest,
            "provider": settings.provider,
            "answer_model": ctx.agent.gateway.model,
            "agent_model": ctx.agent.agent_gateway.model,
            "agent_provider_status": ctx.agent.agent_gateway.status,
            "qa_index": ctx.retriever.qa.manifest,
            "generation": "grounded_synthesis" if settings.provider == "compatible" else "extractive_offline",
            "qa_enabled": settings.qa_enabled,
            "dense": bool(ctx.retriever.dense),
            "exploration_index_ready": ctx.retriever.exploration_ready(),
            "embedding_model": settings.embedding_model.replace("\\", "/").split("/")[-1]
            if ctx.retriever.dense
            else None,
            "reranker": "cross_encoder" if ctx.agent.reranker.reranker else "coverage_heuristic",
            "neo4j": ctx.neo4j.status,
            "redis": ctx.memory_service.redis_status,
            "database": settings.database_backend,
            "memory_layers": 4,
            "pubmed": settings.pubmed_enabled,
            "max_iterations": settings.max_iterations,
            "retrieval_k": settings.retrieval_k, "context_k": settings.context_k,
            "max_model_calls": settings.max_model_calls, "request_timeout": settings.request_timeout,
            "max_concurrent_chats": settings.max_concurrent_chats,
            "requests_per_minute": settings.requests_per_minute,
            "user_model_base_urls": ctx.user_model_service.allowed(),
            "warnings": ctx.retriever.warnings + ctx.agent.reranker.warnings,
        }

    def evaluation(self, owner=Depends(get_admin_owner)):
        report = self.context.settings.reports_dir / "evaluation.json"
        if not report.exists():
            return {"available": False, "message": "尚未运行评测"}
        data = json.loads(report.read_text(encoding="utf-8"))
        data["stale"] = data.get("corpus_version") != self.context.corpus.manifest["version"] or data.get(
            "qa_generation"
        ) != self.context.retriever.qa.manifest.get("generation")
        quality = self.context.settings.reports_dir / "answer-quality.json"
        if quality.exists():
            data["answer_quality"] = json.loads(quality.read_text(encoding="utf-8"))
            data["answer_quality"]["stale"] = (
                data["answer_quality"]["corpus_version"] != self.context.corpus.manifest["version"]
            )
        return {"available": True, **data}

    def metrics(self, owner=Depends(get_admin_owner)):
        values = self.context.chat_dao.metrics()
        return Response(
            "# TYPE mediatlas_runs gauge\n"
            + "\n".join(f'mediatlas_runs{{status="{key}"}} {value}' for key, value in sorted(values.items()))
            + "\n",
            media_type="text/plain",
        )
