from typing import Any

from pydantic import BaseModel, Field


class ErrorFieldDetail(BaseModel):
    loc: list[str | int]
    message: str
    type: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[ErrorFieldDetail
                  | dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorDetail
