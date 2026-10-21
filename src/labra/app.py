from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from labra import __version__
from labra import models as _all_tables  # noqa: F401  (registers every table)
from labra.auth.deps import csrf_protect
from labra.auth.routes import router as auth_router
from labra.billing.routes import router as billing_router
from labra.catalog.routes import router as catalog_router
from labra.core import health, metrics
from labra.core.config import get_settings
from labra.core.logging import configure_logging, get_logger
from labra.core.registry import get_platform
from labra.extlabs.routes import router as extlabs_router
from labra.help.routes import router as help_router
from labra.ops.routes import router as ops_router
from labra.org.routes import router as org_router
from labra.owner.routes import router as owner_router
from labra.patients.routes import router as patients_router
from labra.printing.routes import router as printing_router
from labra.reports.routes import public as reports_public
from labra.reports.routes import router as reports_router
from labra.results.routes import router as results_router
from labra.visits.routes import router as visits_router
from labra.web import errors
from labra.web.middleware import RequestContextMiddleware
from labra.web.templating import PACKAGE


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Build every platform adapter now: a bad setting stops startup, not the first request.
    platform = get_platform()
    get_logger("labra").info(
        "startup",
        version=__version__,
        identity=type(platform.identity).__name__,
        filestore=type(platform.filestore).__name__,
        errors=type(platform.errors).__name__,
        heartbeat=type(platform.heartbeat).__name__,
        mailer=type(platform.mailer).__name__,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_format, settings.log_level)
    app = FastAPI(
        title="Labra",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        dependencies=[Depends(csrf_protect)],
    )
    errors.install(app)
    app.include_router(health.router)
    if settings.metrics == "prometheus":
        app.include_router(metrics.router)
        app.add_middleware(metrics.MetricsMiddleware)
    app.include_router(auth_router)
    app.include_router(org_router)
    app.include_router(catalog_router)
    app.include_router(extlabs_router)
    app.include_router(patients_router)
    app.include_router(visits_router)
    app.include_router(billing_router)
    app.include_router(results_router)
    app.include_router(printing_router)
    app.include_router(reports_router)
    app.include_router(reports_public)
    app.include_router(owner_router)
    app.include_router(ops_router)
    app.include_router(help_router)
    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    # Added last, so it runs first: everything inside sees the request ID.
    app.add_middleware(RequestContextMiddleware, on_error=errors.unexpected_error)
    return app
