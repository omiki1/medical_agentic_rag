import re

from pydantic import BaseModel, Field, field_validator


class LoginEntity(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, email):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("邮箱格式不正确")
        return email.lower()


class RegisterEntity(LoginEntity):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=10, max_length=128)
