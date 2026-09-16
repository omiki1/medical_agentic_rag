from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Document(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    source_id: str
    title: str
    text: str
    entity: str = ""
    facet: str = "overview"
    source_title: str
    source_url: str = ""
    source_type: Literal["public_health", "legacy", "qa", "research"] = "legacy"
    review_status: Literal["source_checked", "unreviewed", "withdrawn"] = "unreviewed"
    published_at: date | None = None
    checked_at: date | None = None
    version: str = "1"
    aliases: list[str] = Field(default_factory=list)
    source_file: str = ""
    source_line: int | None = None
    split: str = ""
    language: str = "zh"
    date_provenance: str = "provided"

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        if value and not value.startswith("https://"):
            raise ValueError("Source links must use HTTPS")
        return value


class Evidence(BaseModel):
    document: Document
    methods: list[str] = Field(default_factory=list)
    raw_scores: dict[str, float] = Field(default_factory=dict)
    fusion_score: float = 0
    fusion_contributions: dict[str, float] = Field(default_factory=dict)
    relevance: float = 0
    rank: int = 0
    graph_paths: list[list[str]] = Field(default_factory=list)
    citation_id: str = ""
