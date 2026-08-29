from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smart_email_manager import __version__
from smart_email_manager.api.problems import ApiProblem, api_problem_handler
from smart_email_manager.api.routers import (
    accounts,
    audit,
    auth,
    codes,
    fleet,
    forwarding,
    imports,
    jobs,
    mail,
    organization,
    projects,
    proxies,
    refresh,
    retention,
    security,
    shares,
    system,
)
from smart_email_manager.config import get_settings
from smart_email_manager.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Smart Email Manager API",
        version=__version__,
        openapi_version="3.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_exception_handler(ApiProblem, api_problem_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )

    prefix = "/api/v1"
    app.include_router(system.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(accounts.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)
    app.include_router(imports.router, prefix=prefix)
    app.include_router(organization.router, prefix=prefix)
    app.include_router(mail.router, prefix=prefix)
    app.include_router(codes.router, prefix=prefix)
    app.include_router(proxies.router, prefix=prefix)
    app.include_router(projects.router, prefix=prefix)
    app.include_router(refresh.router, prefix=prefix)
    app.include_router(retention.router, prefix=prefix)
    app.include_router(security.router, prefix=prefix)
    app.include_router(shares.router, prefix=prefix)
    app.include_router(fleet.router, prefix=prefix)
    app.include_router(forwarding.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    return app


app = create_app()
