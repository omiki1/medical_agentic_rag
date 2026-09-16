from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MemoryRequest(BaseModel):
    kind: Literal["response_style", "learning_focus", "background"]
    value: str = Field(min_length=1, max_length=500)
    confirmed: Literal[True]

    @field_validator("value")
    @classmethod
    def valid_value(cls, value):
        if not value.strip():
            raise ValueError("记忆内容不能为空")
        return value.strip()
