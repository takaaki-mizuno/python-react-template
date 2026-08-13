from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProblemError(BaseModel):
    model_config = ConfigDict(extra="allow")

    location: str | None = None
    pointer: str | None = None
    parameter: str | None = None
    detail: str
    code: str | None = None


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str | None = None
    errors: list[ProblemError | dict[str, Any]] | None = Field(default=None)


PROBLEM_DETAILS_SCHEMA_REF = {"$ref": "#/components/schemas/ProblemDetails"}


def problem_response_openapi(description: str = "Problem Details") -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/problem+json": {
                "schema": PROBLEM_DETAILS_SCHEMA_REF,
            },
        },
    }
