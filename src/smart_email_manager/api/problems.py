from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
    instance: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ApiProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.problem = ProblemDetail(
            title=title,
            status=status,
            detail=detail,
            code=code,
            context=context or {},
        )


async def api_problem_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiProblem):
        raise exc
    problem = exc.problem.model_copy(update={"instance": request.url.path})
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
    )
