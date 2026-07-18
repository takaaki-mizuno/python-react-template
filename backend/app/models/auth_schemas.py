from uuid import UUID

from pydantic import EmailStr, Field
from sqlmodel import SQLModel


class RegisterRequest(SQLModel):
    email: EmailStr
    # Use pydantic.Field for request validation, not SQLModel.Field.
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(SQLModel):
    email: EmailStr
    password: str = Field(max_length=128)


class AuthUserResponse(SQLModel):
    id: UUID
    email: EmailStr


class CsrfTokenResponse(SQLModel):
    csrfToken: str
