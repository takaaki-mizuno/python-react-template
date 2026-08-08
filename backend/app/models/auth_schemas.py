from uuid import UUID

from pydantic import EmailStr, Field
from pydantic.alias_generators import to_camel
from sqlmodel import SQLModel
from sqlmodel.main import SQLModelConfig


class AuthSchema(SQLModel):
    model_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class RegisterRequest(SQLModel):
    email: EmailStr
    # Use pydantic.Field for request validation, not SQLModel.Field.
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(SQLModel):
    email: EmailStr
    password: str = Field(max_length=128)


class AccountDeletionRequest(AuthSchema):
    confirm_email: EmailStr
    password: str | None = Field(default=None, max_length=128)


class AuthUserResponse(SQLModel):
    id: UUID
    email: EmailStr
    roles: list[str]
    permissions: list[str]


class CsrfTokenResponse(SQLModel):
    csrfToken: str
