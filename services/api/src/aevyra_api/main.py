import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from aevyra_api.accounts import RedisRateLimiter
from aevyra_api.commercial.events import PaymentEventProcessor
from aevyra_api.commercial.fulfillment import SynchronousFulfillment
from aevyra_api.commercial.orders import OrderService
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.database import DependencyChecks
from aevyra_api.logging import configure_logging, request_id_context
from aevyra_api.payments.mock import MockPaymentProvider
from aevyra_api.routes import (
    accounts,
    commercial,
    custom_models,
    health,
    preferences,
    research,
    scoring,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        checks = DependencyChecks(config)
        application.state.checks = checks
        application.state.sessions = checks.sessions
        application.state.settings = config
        application.state.rate_limiter = RedisRateLimiter(checks.redis)
        application.state.credit_registry = scoring.registry
        provider = MockPaymentProvider(secrets.token_bytes(32))
        application.state.mock_provider = provider
        application.state.orders = OrderService(checks.sessions, provider)
        application.state.fulfillment = SynchronousFulfillment(
            checks.sessions, scoring.registry, production=config.api_environment == "production"
        )
        application.state.payment_events = PaymentEventProcessor(
            checks.sessions, application.state.fulfillment
        )
        try:
            yield
        finally:
            checks.close()

    application = FastAPI(
        title="Auvylen API",
        version="0.1.0",
        debug=False,
        lifespan=lifespan,
        docs_url=None if config.api_environment == "production" or config.public_pilot else "/docs",
        openapi_url=None
        if config.api_environment == "production" or config.public_pilot
        else "/openapi.json",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID"],
    )

    @application.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Generate IDs internally instead of trusting caller-controlled log contents.
        request_id = str(uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            if request.url.path.startswith(
                (
                    "/api/v1/auth",
                    "/api/v1/account",
                    "/api/v1/redeem",
                    "/api/v1/credit-",
                    "/api/v1/research",
                )
            ):
                response.headers["Cache-Control"] = "no-store"
            logging.getLogger("aevyra.requests").info(
                "request_completed", extra={"status_code": response.status_code}
            )
            return response
        finally:
            request_id_context.reset(token)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("aevyra.errors").error(
            "unhandled_error",
            extra={"error_type": type(exc).__name__, "request_id": request.state.request_id},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers={"X-Request-ID": request.state.request_id},
        )

    @application.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={"X-Request-ID": request.state.request_id},
        )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's default error payload includes rejected input (passwords/codes).
        return JSONResponse(status_code=422, content={"detail": "Invalid request fields"})

    application.include_router(health.router)
    application.include_router(scoring.router)
    application.include_router(commercial.router)
    application.include_router(accounts.router)
    application.include_router(research.router)
    application.include_router(preferences.router)
    application.include_router(custom_models.router)
    return application


app = create_app()
