from pydantic import BaseModel, ConfigDict, Field

from agent.QueryAnalyzer import make_plan


class PlanSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=400)
    use_graph: bool


class RetrievalPlanner:
    """显式路由；计划与检索实现分离。"""

    def __init__(self, settings):
        self.settings = settings

    def plan(self, analysis, dense_available):
        return make_plan(analysis, self.settings, dense_available)

    async def refine(self, analysis, plan, gateway, budget):
        if (
            self.settings.provider != "compatible"
            or analysis.personal_treatment
            or analysis.constraints
            or (len(analysis.entities) == 1 and len(analysis.query) < 90)
        ):
            return plan, analysis.query, "orchestrated"
        try:
            raw = await gateway.json(
                '为医学检索规划查询。返回 {"query":"检索关键词","use_graph":true}。'
                "保留原问题的疾病与请求维度，不推断诊断。图谱仅在 graph_allowed 为 true 时可启用。",
                {
                    "question": analysis.query,
                    "entities": analysis.entities,
                    "facets": analysis.facets,
                    "graph_allowed": plan.use_graph,
                },
                budget,
            )
            selected = PlanSelection.model_validate(raw)
            if selected.use_graph and not plan.use_graph:
                raise ValueError("Graph route was not authorized")
            plan = plan.model_copy(update={"use_graph": selected.use_graph})
            if not selected.use_graph:
                plan.routes = [route for route in plan.routes if route != "graph"]
            return plan, (" ".join(analysis.entities) + " " + selected.query).strip(), "bounded_model"
        except Exception:
            return plan, analysis.query, "orchestrated_fallback"
