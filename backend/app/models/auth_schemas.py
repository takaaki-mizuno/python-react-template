from uuid import UUID

from pydantic import EmailStr, Field, field_validator
from sqlmodel import SQLModel
from sqlmodel.main import SQLModelConfig

from app.models.language import DEFAULT_LANGUAGE_CODE, LanguageCode


class AuthSchema(SQLModel):
    model_config = SQLModelConfig(extra="forbid")


class RegisterRequest(AuthSchema):
    email: EmailStr
    # Use pydantic.Field for request validation, not SQLModel.Field.
    password: str = Field(min_length=12, max_length=128)
    language_code: LanguageCode = DEFAULT_LANGUAGE_CODE


class LoginRequest(AuthSchema):
    email: EmailStr
    password: str = Field(max_length=128)


class AccountDeletionRequest(AuthSchema):
    confirm_email: EmailStr
    password: str | None = Field(default=None, max_length=128)


class UpdateAuthUserRequest(AuthSchema):
    language_code: LanguageCode | None = Field(default=None)

    @field_validator("language_code", mode="before")
    @classmethod
    def reject_null_for_non_nullable_patch_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null.")
        return value


class AuthUserResponse(AuthSchema):
    id: UUID
    email: EmailStr
    language_code: LanguageCode
    roles: list[str]
    permissions: list[str]


class CsrfTokenResponse(AuthSchema):
    csrf_token: str


class OidcProviderResponse(AuthSchema):
    provider_id: str
    display_name: str


class OidcProviderListResponse(AuthSchema):
    data: list[OidcProviderResponse]
