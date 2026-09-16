import math
import threading

from agent.EvidencePolicy import EvidencePolicy
from agent.QueryTopics import QueryTopics

from rag.BM25Retriever import tokenize


class Reranker:
    def __init__(self, settings):
        self.settings = settings
        self.reranker = None
        self.model_lock = threading.Lock()
        self.warnings = []
        self.last_predictions_used = False  # True only if the cross-encoder ran this call
        self.last_predictions_error = ""
        if settings.reranker_model:
            try:
                from sentence_transformers import CrossEncoder

                self.reranker = CrossEncoder(
                    settings.reranker_model,
                    device=settings.model_device,
                    local_files_only=True,
                    max_length=384,
                )
            except Exception as error:
                self.warnings.append("Cross-encoder unavailable: " + type(error).__name__)

    def rerank(self, query, evidence, analysis, k=None):
        if not evidence:
            return []
        q = QueryTopics.tokens(query)
        predictions = None
        self.last_predictions_used = False
        self.last_predictions_error = ""
        if self.reranker:
            try:
                with self.model_lock:
                    predictions = self.reranker.predict(
                        [(query, e.document.text) for e in evidence], batch_size=8, show_progress_bar=False
                    )
                self.last_predictions_used = True
            except Exception as error:
                self.last_predictions_error = type(error).__name__
        for i, ev in enumerate(evidence):
            d = ev.document
            overlap = len(q & set(tokenize(d.title + d.text))) / max(1, len(q))
            topic_coverage = QueryTopics.coverage(d, analysis.topic_groups)
            entity_match = bool(analysis.entities) and any(
                EvidencePolicy.entity_matches(d, entity) for entity in analysis.entities
            )
            broad_overview = QueryTopics.broad_overview(analysis)
            if broad_overview:
                # A question like "晚上总做梦睡不好是正常的吗？" matches no facet word and
                # defaults to overview, but any facet of the topic (cause/prevention/symptom)
                # is a legitimate match. Don't let overview-only docs outrank the real cause
                # or prevention material just because they happen to carry the overview facet.
                facet_match = True
            else:
                facet_match = any(
                    EvidencePolicy.facet_matches(d, facet, analysis.mode) for facet in analysis.facets
                )
            ev.relevance = (
                0.4 * overlap + 0.35 * max(topic_coverage, float(entity_match)) + 0.25 * facet_match
            )
            ev.raw_scores["topic_coverage"] = round(topic_coverage, 4)
            ev.raw_scores["coverage_heuristic"] = round(ev.relevance, 4)
            if predictions is not None:
                score = float(predictions[i])
                ev.raw_scores["cross_encoder_logit"] = score
                ev.relevance = 0.5 * ev.relevance + 0.5 / (1 + math.exp(-max(-40, min(40, score))))
            ev.relevance = round(ev.relevance, 4)
        evidence.sort(
            key=lambda e: (
                -QueryTopics.subject_coverage(e.document, analysis.topic_groups),
                e.document.facet not in analysis.facets if not broad_overview else False,
                not any(EvidencePolicy.facet_matches(e.document, f, analysis.mode) for f in analysis.facets)
                if not broad_overview
                else False,
                e.document.review_status != "source_checked",
                -e.relevance,
                -e.fusion_score,
                e.document.id,
            )
        )
        result = []
        for entity in analysis.entities:
            for facet in analysis.facets:
                candidate = next(
                    (
                        ev
                        for ev in evidence
                        if EvidencePolicy.entity_matches(ev.document, entity)
                        and (
                            broad_overview or EvidencePolicy.facet_matches(ev.document, facet, analysis.mode)
                        )
                    ),
                    None,
                )
                if candidate and candidate not in result:
                    result.append(candidate)
        result += [ev for ev in evidence if ev not in result]
        result = result[: k or self.settings.context_k]
        for i, ev in enumerate(result, 1):
            ev.rank = i
            ev.citation_id = f"E{i}"
        return result
