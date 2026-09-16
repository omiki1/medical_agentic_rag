"""A bounded, observable agent state machine.

Trace events describe executed actions, not hidden model reasoning. Medical
content is buffered until evidence AND answer gates have accepted it.
"""

import re
import time

from ai.LLMService import LLMService
from ai.PubMedService import PubMedService
from common.TranslationService import is_english
from rag.service.RAGService import RAGService

from agent.AnswerGrader import AnswerGrader
from agent.entity.AgentState import Claim, Draft, RunResult, TraceEvent
from agent.EvidencePolicy import EvidencePolicy
from agent.GroundedAnswerService import GroundedAnswerService
from agent.QueryAnalyzer import QueryAnalyzer
from agent.ReflectionService import ReflectionService
from agent.RetrievalPlanner import RetrievalPlanner
import agent.SafetyRouter as SafetyRouter

DISCLAIMER = "以上内容仅供医学科普参考，不构成个体诊断或处方。"
EMERGENCY_ANSWER = "你描述的情况可能需要紧急医疗处理。请立即联系当地急救服务或前往急诊，不要等待在线问答。若在中国大陆可拨打 120，在日本可拨打 119。"
URGENT_ANSWER_PREFIX = "你描述的情况建议尽快就医或联系医生评估，不要仅依赖在线信息拖延处理。"

_GENERATION_FAILURE_HINTS = {
    "provider": "本次解释服务调用超时或暂不可用，请稍后重试；已找到的资料可在来源面板查看。",
    "schema": "本次生成的结构未通过校验，未展示可能不完整的解释；可以重试或缩小问题范围。",
    "semantic_review": "生成的解释未通过切题性与依据独立检查，未展示可能误导的内容；可查看来源面板中的原始资料。",
    "citations": "生成的解释引用未通过原文校验，未展示可能无依据的表述；可查看来源面板中的原始资料。",
}

# 比 stage 更精确的失败原因。原先所有 provider 失败都说"超时或暂不可用"，
# 但线上实际遇到的是"模型返回内容无法解析"——不是超时也不是服务不可用，
# 会把人引向查网络，而真正该做的是换模型。这里按原因给准确且可操作的提示。
_GENERATION_FAILURE_REASONS = {
    "model_output": "模型返回的内容无法按约定格式解析，未展示可能不完整的解释；"
    "已找到的资料可在来源面板查看。建议在「模型设置」中更换模型后重试。",
    "timeout": "模型响应超时，未展示可能不完整的解释；已找到的资料可在来源面板查看。"
    "可稍后重试，或改用响应更快的模型。",
    "auth": "模型服务拒绝了当前 API Key，请在「模型设置」中确认密钥有效、且属于所选服务商；"
    "已找到的资料可在来源面板查看。",
    "rate_limited": "模型服务当前限流，请稍后重试；已找到的资料可在来源面板查看。",
    "network": "无法连接模型服务，请检查网络或服务地址是否正确；已找到的资料可在来源面板查看。",
    "http_status": "模型服务返回错误，请稍后重试或更换模型；已找到的资料可在来源面板查看。",
}


def _generation_failure_message(attempts) -> str:
    """User-facing reason for a failed synthesis, kept distinct from '证据不足'."""
    if not attempts:
        return "已找到相关资料，但本次解释未完成或未通过质量检查。你可以稍后重试，或在来源面板中查看资料及其核验状态。"
    last = attempts[-1]
    # 先看更精确的原因，再看粗粒度阶段。
    reason_hint = _GENERATION_FAILURE_REASONS.get(last.get("reason", ""), "")
    if reason_hint:
        return reason_hint
    hint = _GENERATION_FAILURE_HINTS.get(last.get("stage", ""), "")
    if hint:
        return hint
    return "已找到相关资料，但本次解释未完成或未通过质量检查。你可以稍后重试，或在来源面板中查看资料及其核验状态。"

SENTENCE_END = re.compile(r"[。！？!?]|(?<=\.)\s+(?=[A-Z])|\n")


def excerpt(text: str, max_chars: int = 280) -> str:
    """A contiguous source excerpt that ends at a sentence boundary.

    Quotes must remain substrings of the original document, so the excerpt is
    always a literal prefix of the source text — never a re-joined fragment
    that starts or ends mid-word.
    """
    text = text.strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    boundaries = [match.end() for match in SENTENCE_END.finditer(text) if match.end() <= max_chars]
    if boundaries:
        cut = max(boundaries)
        return text[:cut].strip()
    # No terminator before the cap: for Latin text cut at the last word space,
    # otherwise accept the hard cut rather than emitting nothing.
    ascii_text = re.fullmatch(r"[A-Za-z0-9 .,;:'\"()%/-]+", text[: max_chars + 1])
    if ascii_text:
        truncated = text[:max_chars]
        space = truncated.rfind(" ")
        return truncated[:space].strip() if space > 0 else truncated
    return text[:max_chars].strip()


class MedicalAgent:
    def __init__(self, corpus, retriever, settings, graph=None, gateway=None, translator=None):
        self.corpus, self.retriever, self.settings, self.graph = corpus, retriever, settings, graph
        self.translator = translator
        self.analyzer = QueryAnalyzer(corpus)
        self.planner = RetrievalPlanner(settings)
        self.rag = RAGService(corpus, retriever, settings, graph)
        self.reranker = self.rag.reranker
        self.answer_grader = AnswerGrader()
        self.gateway = gateway or LLMService(settings)
        self.pubmed = PubMedService(settings)
        self.agent_gateway = gateway or LLMService(settings, role="agent")
        self.reflection = ReflectionService(settings, self.agent_gateway)
        self.answers = GroundedAnswerService(self.gateway, self.agent_gateway, settings)
        from memory.layers.ConversationState import ContextResolver

        self.memory_resolver = ContextResolver()

    async def stream(
        self,
        question,
        run_id,
        previous_question="",
        *,
        fixed=False,
        memory=None,
        retrieval_mode="hybrid",
        graph_enabled=True,
        conversation_id="",
        mode="authoritative",
    ):
        start = time.perf_counter()
        trace, warnings = [], list(self.retriever.warnings) + self.reranker.warnings
        budget = {"calls": 0, "session_id": conversation_id or run_id}
        iteration = 0

        def event(step, label, detail=None, status="ok"):
            item = TraceEvent(
                sequence=len(trace) + 1,
                step=step,
                label=label,
                status=status,
                elapsed_ms=round((time.perf_counter() - start) * 1000),
                iteration=iteration,
                detail=detail or {},
            )
            trace.append(item)
            return {"type": "trace", "data": item.model_dump()}

        if memory:
            previous_question = memory.previous_question
            yield event("memory", "读取四层记忆上下文", memory.trace())
        analysis = self.analyzer.analyze(question, previous_question)
        analysis.mode = mode
        # Risk change check over the established patient context: if the current
        # utterance has no standalone risk but continues an earlier risk story
        # (e.g. "肚脐疼" -> "现在移到右下腹更疼"), the previous turn's content is
        # folded into the router so the escalation is not missed.
        if (
            analysis.risk_level == SafetyRouter.NONE
            and memory
            and memory.recent
            and not analysis.out_of_scope
            and not analysis.entities
            and re.search(
                r"现在|更|比刚才|又|还是|转移|移到|加重|厉害|继续|持续|走路|一震|一碰",
                question,
            )
        ):
            # Continuation of an earlier symptom story (e.g. "肚脐疼" -> "现在移到
            # 右下腹更疼，走路一震就疼"): fold the prior utterance in so the
            # escalation to an urgent band is not lost. Topic switches with their own
            # entities are excluded above.
            prior_text = ""
            for turn in reversed(memory.recent):
                if turn.outcome in {"answered", "abstained", "clarification"} and turn.question:
                    prior_text = turn.question
                    break
            if prior_text:
                merged = prior_text + "。" + analysis.original
                from agent.SafetyRouter import classify as _classify_risk

                risk = _classify_risk(merged)
                if risk.level != SafetyRouter.NONE:
                    analysis.risk_level = risk.level
                    analysis.risk_code = risk.code
                    analysis.risk_band_message = risk.band_message
                    if risk.level == SafetyRouter.EMERGENCY:
                        analysis.emergency = True
                        if risk.code not in analysis.emergency_terms:
                            analysis.emergency_terms.append(risk.code)
        yield event(
            "analyze",
            "识别问题与安全检查",
            {
                "intent": analysis.intent,
                "entities": analysis.entities,
                "facets": analysis.facets,
                "contextualized": analysis.contextualized,
                "mode": mode,
                "topic_groups": analysis.topic_groups,
            },
        )
        result = RunResult(
            run_id=run_id,
            mode=mode,
            status="abstained",
            answer="",
            analysis=analysis,
            corpus_version=self.corpus.manifest["version"],
        )
        # Pure recall questions ("我刚才说多久了？" "说的是我还是我妈？") are answered
        # straight from the user-provided conversation state - no medical lookup, no
        # model call - so durable memory actually participates in understanding.
        # Risk routing still wins: a recall phrasing that also carries a fresh
        # emergency signal is not allowed to suppress the safety prompt.
        recall_answer = None
        if (
            memory
            and getattr(memory, "conversation_state", None)
            and not analysis.emergency
            and analysis.risk_level == SafetyRouter.NONE
        ):
            recall_answer = self.memory_resolver.recall_answer(
                memory.conversation_state, question
            )
        if recall_answer:
            result.status = "answered"
            result.answer = recall_answer + "\n\n" + DISCLAIMER
            result.model_calls = 0
            yield event(
                "memory_recall",
                "从会话事实直接回答",
                {"recall": recall_answer},
                "ok",
            )
        elif analysis.emergency:
            result.status, result.answer = "emergency", EMERGENCY_ANSWER
            yield event(
                "safety",
                "急症信号：立即就医",
                {"signals": analysis.emergency_terms, "risk_level": analysis.risk_level, "risk_code": analysis.risk_code},
                "blocked",
            )
        elif analysis.risk_level == SafetyRouter.URGENT:
            # Explicit "seek care soon" band: the prompt must survive even if the
            # downstream generation fails, so we emit it directly with the matched
            # composite-signal message (never a generic "证据不足" placeholder).
            message = analysis.risk_band_message or URGENT_ANSWER_PREFIX
            result.status = "answered"
            result.answer = (
                URGENT_ANSWER_PREFIX + "\n\n" + message + "\n\n" + DISCLAIMER
            )
            yield event(
                "safety",
                "建议尽快就医",
                {"risk_level": analysis.risk_level, "risk_code": analysis.risk_code},
                "warning",
            )
        elif analysis.fabrication_request:
            result.answer = (
                "不能编造论文、病例或医学证据。可以改为查找真实来源，并说明现有证据支持什么、尚不能说明什么。"
            )
            yield event("scope", "拒绝伪造医学证据", status="blocked")
        elif analysis.needs_clarification:
            result.status = "clarification"
            result.answer = (
                analysis.clarification_prompt
                or "请补充你想了解的疾病或症状，以及需要了解的是症状、检查还是预防。"
            )
            yield event("clarify", "需要补充问题背景", status="warning")
        elif analysis.out_of_scope:
            result.status = "out_of_scope"
            result.answer = (
                "这个工作台用于医学资料检索。可以询问疾病的症状、检查或预防，也可以在知识库中查找具体条目。"
            )
            yield event("scope", "问题超出知识库范围", status="blocked")
        else:
            plan = self.planner.plan(analysis, self.retriever.dense is not None)
            query, plan_source = analysis.query, "orchestrated"
            if not fixed:
                plan, query, plan_source = await self.planner.refine(
                    analysis, plan, self.agent_gateway, budget
                )
            if not graph_enabled:
                plan.use_graph = False
                plan.routes = [r for r in plan.routes if r != "graph"]
            result.plan = plan
            yield event("plan", "制定检索计划", {**plan.model_dump(), "decision_source": plan_source})
            fingerprints = set()
            hyde_used = False
            pubmed_tried = False
            evidence = []
            hypothesis = ""
            for iteration in range(1, (1 if fixed else self.settings.max_iterations) + 1):
                result.iterations = iteration
                evidence, grade, observation = await self.rag.retrieve(
                    query, analysis, plan, mode=retrieval_mode, hypothesis=hypothesis
                )
                yield event(
                    "action",
                    "执行受限检索工具",
                    {
                        "routes": plan.routes,
                        "query": query,
                        "hypothesis_used": bool(hypothesis),
                        "read_only": True,
                    },
                )
                yield event("observe", "观察检索结果与来源覆盖", observation)
                result.evidence, result.evidence_grade = evidence, grade
                yield event(
                    "grade_evidence",
                    "证据满足要求" if grade.sufficient else "发现证据缺口",
                    grade.model_dump(),
                    "ok" if grade.sufficient else "warning",
                )
                # PubMed supplements local evidence for "latest/今年" questions when the
                # local corpus leaves a coverage gap; results join this round's evidence
                # so generation (and citations) can actually use them, not just display.
                if plan.use_pubmed and not grade.sufficient and iteration == 1 and not pubmed_tried:
                    pubmed_tried = True
                    try:
                        literature = await self.pubmed.search(analysis.entities)
                        if literature:
                            for lit in literature:
                                lit.relevance = 0.6
                                if lit.document.id not in {e.document.id for e in evidence}:
                                    evidence.append(lit)
                            # Reassign citation ids so the appended research abstracts get
                            # E-numbers (PubMed docs bypass rerank which normally assigns them).
                            for rank, ev in enumerate(evidence, 1):
                                ev.rank = rank
                                ev.citation_id = f"E{rank}"
                            result.evidence = evidence
                            grade = self.rag.grader.grade(analysis, evidence)
                            yield event(
                                "pubmed",
                                "检索公开文献线索",
                                {"count": len(literature), "clinical_review": "required"},
                            )
                            yield event(
                                "grade_evidence",
                                "加入公开文献后重新判定证据",
                                grade.model_dump(),
                                "ok" if grade.sufficient else "warning",
                            )
                    except Exception as exc:
                        warnings.append("PubMed 不可用：" + type(exc).__name__)
                        yield event("pubmed", "公开文献服务暂不可用", status="warning")
                if grade.sufficient:
                    eligible = [e for e in evidence if e.document.id in grade.eligible_ids]
                    draft, answer_grade, generation = None, None, "extractive"
                    if self.settings.provider == "compatible":
                        yield event(
                            "generate", "基于证据组织解释并检查切题性", {"style": "grounded_synthesis"}
                        )
                        draft, answer_grade, attempts = await self.answers.generate(
                            eligible, analysis, budget, memory
                        )
                        for attempt in attempts:
                            yield event("repair_answer", "检查生成内容并反馈修正", attempt, "warning")
                        if draft:
                            generation = "grounded_synthesis"
                        if draft is None:
                            # A failed semantic check must never be bypassed by displaying
                            # the same unreviewed facts as literal excerpts.
                            result.generation_mode = "generation_unavailable"
                            result.answer = _generation_failure_message(attempts)
                            warnings.append("生成检查失败，未自动转为原文摘录")
                            yield event(
                                "grade_answer",
                                "解释未通过检查，未展示未经验证的答案",
                                {"verification": "failed", "attempts": attempts},
                                "blocked",
                            )
                            break
                    if draft is None:
                        draft = self.extract(eligible, analysis, memory)
                        answer_grade = self.answer_grader.grade(draft, eligible, analysis)
                    result.answer_grade = answer_grade
                    yield event(
                        "grade_answer",
                        "检查引用、切题性与结论支持",
                        answer_grade.model_dump(),
                        "ok" if answer_grade.passed else "blocked",
                    )
                    if answer_grade.passed:
                        result.status = "answered"
                        result.generation_mode = generation
                        result.answer = await self.render(draft, eligible, analysis)
                        if generation == "extractive_fallback":
                            result.answer = (
                                "本次解释生成未完成，以下仅展示已找到的相关原文：\n\n" + result.answer
                            )
                    else:
                        result.answer = (
                            "答案未通过引用校验，暂不展示可能造成误导的内容。可以缩小问题范围后再试。"
                        )
                    break
                fingerprint = tuple(sorted(e.document.id for e in evidence))
                progressed = fingerprint not in fingerprints
                fingerprints.add(fingerprint)
                if fixed:
                    break
                decision, origin = await self.reflection.reflect(
                    analysis,
                    grade,
                    iteration,
                    progressed,
                    self.retriever.dense is not None,
                    hyde_used,
                    budget,
                )
                yield event(
                    "reflect",
                    "根据缺口检查下一步行动",
                    {
                        "decision": decision.action,
                        "reason_code": decision.reason_code,
                        "decision_source": origin,
                        "progressed": progressed,
                        "remaining_rounds": self.settings.max_iterations - iteration,
                    },
                )
                if decision.action == "stop":
                    yield event(
                        "stop", "已达到本次检索的回答边界", {"reason": decision.reason_code}, "warning"
                    )
                    break
                if decision.action == "hyde":
                    hypothesis, hyde_used = decision.query, True
                else:
                    if decision.query == query:
                        yield event("stop", "检索条件没有变化", {"reason": "unchanged_query"}, "warning")
                        break
                    query, hypothesis = decision.query, ""
            # PubMed was consulted inside the loop when the local corpus left a gap
            # (see the pubmed_tried block above); nothing to repeat after the loop.
            if not result.answer:
                missing = result.evidence_grade.missing if result.evidence_grade else []
                result.answer = "当前资料不足以可靠回答这个问题。"
                if analysis.personal_treatment:
                    result.answer = "不能仅凭这条描述决定个人用药或剂量，也不应自行更改处方药的服用方案。请把药名、规格、目前用法、症状和相关检查结果交给医生或药师评估；年龄、孕期或哺乳情况及其他用药也需要一并说明。"
                elif missing:
                    result.answer += "\n\n尚缺：" + "；".join(missing[:4]) + "。"
                if not analysis.personal_treatment:
                    result.answer += "\n\n你可以查看已有来源，或把问题缩小到某种疾病的基础知识。"
        if not result.answer.endswith(DISCLAIMER):
            result.answer = result.answer.rstrip() + "\n\n" + DISCLAIMER
        yield event(
            "complete",
            "回答已验证" if result.status == "answered" else "已明确回答边界",
            {"status": result.status},
        )
        result.trace = trace
        result.warnings = list(dict.fromkeys(warnings))
        result.model_calls = budget["calls"]
        result.duration_ms = round((time.perf_counter() - start) * 1000)
        yield {"type": "result", "data": result.model_dump(mode="json")}

    def extract(self, evidence, analysis, memory=None):
        broad = analysis.facets == ["overview"] and not re.search(
            r"是什么|什么是|定义|概念", analysis.original
        )
        direct = evidence if broad else [ev for ev in evidence if ev.document.facet in analysis.facets]
        evidence = direct or evidence
        # In exploration, prefer checked material and never let an unreviewed passage
        # carrying dosing / check-frequency / hormone advice (prescribing_detail) drag a
        # whole answer through the citation gate. Checked docs are used first; legacy
        # docs may still fill topic gaps, but only when their text is safe to quote.
        if analysis.mode == "exploratory":
            checked = [ev for ev in evidence if ev.document.review_status == "source_checked"]
            if checked:
                evidence = checked + [ev for ev in evidence if ev.document.id not in {e.document.id for e in checked}]
        selected = []
        covered = set()
        for ev in evidence:
            d = ev.document
            if not broad and not any(
                EvidencePolicy.facet_matches(d, facet, analysis.mode) for facet in analysis.facets
            ):
                continue
            key = (d.entity, d.facet)
            if key in covered:
                continue
            covered.add(key)
            # Unreviewed passages that carry dosing / check-frequency / hormone advice
            # are quarantined before quoting (same policy as the answer gate), so one
            # legacy fragment cannot fail the whole extractive answer.
            if d.review_status != "source_checked" and EvidencePolicy.prescribing_detail(d.text):
                continue
            # Complete sentences only: a raw prefix can start/end mid-word and
            # drag research-history fragments into the answer (off-topic drift).
            snippet = excerpt(d.text, 280)
            if not snippet:
                continue
            selected.append(Claim(text=snippet, evidence_ids=[d.id], quotes=[snippet]))
        if not selected and analysis.mode == "exploratory":
            qualified = [e for e in evidence if e.document.review_status == "source_checked"]
            for e in (qualified or evidence[:3])[:3]:
                snippet = excerpt(e.document.text, 450)
                if not snippet:
                    continue
                selected.append(Claim(text=snippet, evidence_ids=[e.document.id], quotes=[snippet]))
        if (
            memory
            and analysis.facets == ["overview"]
            and any(m["kind"] == "response_style" and m["value"] == "简洁" for m in memory.semantic)
        ):
            # A preference may change presentation, never evidence or safety gates.
            first_per_entity = {}
            for claim in selected:
                entity = next(e.document.entity for e in evidence if e.document.id == claim.evidence_ids[0])
                first_per_entity.setdefault(entity, claim)
            selected = list(first_per_entity.values())
        return Draft(claims=selected[: 8 if analysis.entities else 2])

    async def render(self, draft, evidence, analysis):
        ids = {e.document.id: e.citation_id for e in evidence}
        budget = {"calls": 0, "session_id": "display"}
        body_parts = []
        for claim in draft.claims:
            text = claim.text
            # Raw English excerpts are translated for display; the original text
            # stays in claim.quotes so citation grading still checks verbatim support.
            if is_english(text) and self.translator and self.translator.available:
                translated = await self.translator.translate(text, "", budget)
                if translated and translated.get("text_zh"):
                    text = translated["text_zh"]
            body_parts.append(text + " " + " ".join(f"[{ids[i]}]" for i in dict.fromkeys(claim.evidence_ids)))
        body = "\n\n".join(body_parts)
        return body + "\n\n" + DISCLAIMER

    async def run(self, question, run_id="evaluation", previous_question="", **options):
        async for event in self.stream(question, run_id, previous_question, **options):
            if event["type"] == "result":
                return RunResult.model_validate(event["data"])
