from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["rewrite", "hyde", "stop"]
    query: str = Field(default="", max_length=400)
    reason_code: Literal["missing_facet", "vocabulary_gap", "insufficient_sources", "no_progress"]


class AgentPolicy:
    """Code, never the model, grants capabilities and enforces the retry budget."""

    def __init__(self, settings):
        self.settings = settings

    def allowed(self, analysis, iteration, progressed, dense_available, hyde_used):
        if (
            analysis.emergency
            or analysis.personal_treatment
            or analysis.constraints
            or iteration >= self.settings.max_iterations
            or not progressed
        ):
            return ["stop"]
        actions = ["rewrite", "stop"]
        if dense_available and not hyde_used:
            actions.insert(1, "hyde")
        return actions

    def validate(self, raw, allowed, analysis):
        decision = AgentDecision.model_validate(raw)
        if decision.action not in allowed:
            raise ValueError("Action is not permitted in this state")
        if decision.action != "stop":
            if not decision.query.strip():
                raise ValueError("Retrieval query is empty")
            # Entity bindings established during perception cannot be replaced by a model.
            decision.query = (" ".join(analysis.entities) + " " + decision.query.strip())[:600]
        return decision
