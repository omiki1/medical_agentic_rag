from typing import Literal

from pydantic import BaseModel, Field
from rag.entity.Evidence import Evidence


class Analysis(BaseModel):
    mode: Literal["authoritative", "exploratory"] = "authoritative"
    original: str
    query: str
    intent: str = "overview"
    entities: list[str] = Field(default_factory=list)
    topic_groups: list[list[str]] = Field(default_factory=list)
    symptom_request: bool = False
    clarification_prompt: str = ""
    facets: list[str] = Field(default_factory=lambda: ["overview"])
    emergency: bool = False
    emergency_terms: list[str] = Field(default_factory=list)
    risk_level: Literal["none", "urgent", "emergency"] = "none"
    risk_code: str = ""
    risk_band_message: str = ""
    out_of_scope: bool = False
    fabrication_request: bool = False
    personal_treatment: bool = False
    needs_clarification: bool = False
    contextualized: bool = False
    wants_latest: bool = False
    constraints: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    routes: list[str]
    reason: str
    use_graph: bool = False
    use_hyde: bool = False
    use_pubmed: bool = False


class EvidenceGrade(BaseModel):
    sufficient: bool = False
    coverage: float = Field(default=0, ge=0, le=1)
    missing: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    eligible_ids: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(min_length=1, max_length=15)
    quotes: list[str] = Field(min_length=1, max_length=15)


class Draft(BaseModel):
    claims: list[Claim] = Field(min_length=1, max_length=8)


class AnswerGrade(BaseModel):
    grounded: bool = False
    relevant: bool = False
    complete: bool = False
    feedback: list[str] = Field(default_factory=list)
    verification: str = "exact_extract"
    supported_claims: int = 0
    total_claims: int = 0

    @property
    def passed(self):
        return (
            self.grounded
            and self.relevant
            and self.complete
            and self.verification != "semantic_review_pending"
        )


class TraceEvent(BaseModel):
    sequence: int
    step: str
    label: str
    status: Literal["ok", "warning", "blocked"] = "ok"
    elapsed_ms: int
    iteration: int = 0
    detail: dict = Field(default_factory=dict)


class RunResult(BaseModel):
    mode: Literal["authoritative", "exploratory"] = "authoritative"
    run_id: str
    status: Literal["answered", "abstained", "emergency", "clarification", "out_of_scope"]
    answer: str
    analysis: Analysis
    plan: Plan | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_grade: EvidenceGrade | None = None
    answer_grade: AnswerGrade | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    iterations: int = 0
    model_calls: int = 0
    duration_ms: int = 0
    warnings: list[str] = Field(default_factory=list)
    corpus_version: str = ""
    generation_mode: str = "extractive"
