from uuid import UUID

from pydantic import Field
from pydantic.alias_generators import to_camel
from sqlmodel import SQLModel
from sqlmodel.main import SQLModelConfig


class AuthorizationSchema(SQLModel):
    model_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class RoleResponse(AuthorizationSchema):
    code: str
    display_name: str
    description: str | None
    permissions: list[str]


class PermissionResponse(AuthorizationSchema):
    code: str
    display_name: str
    description: str | None


class RoleListResponse(AuthorizationSchema):
    roles: list[RoleResponse]
    permissions: list[PermissionResponse]


class UserRoleListResponse(AuthorizationSchema):
    user_id: UUID
    roles: list[str]
    permissions: list[str]


class UserRoleReplaceRequest(AuthorizationSchema):
    roles: list[str] = Field(max_length=100)


class UserRoleReplaceResponse(AuthorizationSchema):
    user_id: UUID
    roles: list[str]
    permissions: list[str]
    granted_roles: list[str]
    revoked_roles: list[str]
