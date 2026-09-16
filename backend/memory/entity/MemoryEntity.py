from pydantic import BaseModel, Field


class RecentTurn(BaseModel):
    run_id: str
    question: str = Field(max_length=2000)
    entities: list[str] = Field(default_factory=list, max_length=6)
    outcome: str


class MemoryWindow(BaseModel):
    owner: str
    conversation_id: str
    revision: str
    turns: list[RecentTurn] = Field(default_factory=list, max_length=20)
