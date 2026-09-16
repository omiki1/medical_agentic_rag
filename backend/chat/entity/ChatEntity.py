from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatEntity(BaseModel):
    mode: Literal["authoritative", "exploratory"] = "authoritative"
    conversation_id: UUID
    request_id: UUID
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def valid_question(cls, value):
        if not value.strip():
            raise ValueError("问题不能为空")
        return value.strip()


class ConversationTitleEntity(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value):
        if not value.strip():
            raise ValueError("标题不能为空")
        return value.strip()
