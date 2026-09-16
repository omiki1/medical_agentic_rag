from agent.AgentPolicy import AgentDecision, AgentPolicy


class ReflectionService:
    """Structured reflection on observable gaps; no free-form chain of thought is stored."""

    def __init__(self, settings, gateway):
        self.settings, self.gateway = settings, gateway
        self.policy = AgentPolicy(settings)

    async def reflect(self, analysis, grade, iteration, progressed, dense, hyde_used, budget):
        allowed = self.policy.allowed(analysis, iteration, progressed, dense, hyde_used)
        if allowed == ["stop"]:
            return AgentDecision(
                action="stop", reason_code="no_progress" if not progressed else "insufficient_sources"
            ), "policy"
        if self.settings.provider == "compatible" and budget["calls"] < self.settings.max_model_calls - 4:
            try:
                raw = await self.gateway.json(
                    "你是只读检索控制器。根据可观察的证据缺口选择下一步。只允许 allowed 中的动作。"
                    "rewrite 改写关键词，hyde 生成假设性检索描述（不是证据），stop 停止。"
                    '返回 {"action":"rewrite|hyde|stop","query":"检索文本",'
                    '"reason_code":"missing_facet|vocabulary_gap|insufficient_sources|no_progress"}。'
                    "不能放宽来源、医疗安全规则，不能指定网址、代码或数据库命令。",
                    {
                        "question": analysis.query,
                        "entities": analysis.entities,
                        "missing": grade.missing,
                        "allowed": allowed,
                        "remaining_rounds": self.settings.max_iterations - iteration,
                    },
                    budget,
                )
                return self.policy.validate(raw, allowed, analysis), "model"
            except Exception:
                # A malformed/denied decision never reaches a tool. Keep a bounded code fallback.
                pass
        query = (analysis.query + " " + " ".join(grade.missing))[:400]
        return AgentDecision(action="rewrite", query=query, reason_code="missing_facet"), "rule_fallback"
