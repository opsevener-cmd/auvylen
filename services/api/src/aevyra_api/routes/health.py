import logging
from typing import Literal, Protocol, cast

from aevyra_contracts import Dependencies, HealthResponse, ReadinessResponse
from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["operations"])
logger = logging.getLogger("aevyra.dependencies")


class Checks(Protocol):
    def database(self) -> None: ...
    def cache(self) -> None: ...


def get_checks(request: Request) -> Checks:
    return cast(Checks, request.app.state.checks)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}}
)
def ready(request: Request, response: Response) -> ReadinessResponse:
    checks = get_checks(request)
    states: dict[str, Literal["ok", "unavailable"]] = {}
    for name, probe in (("database", checks.database), ("redis", checks.cache)):
        try:
            probe()
            states[name] = "ok"
        except Exception as exc:
            # The endpoint remains safe even for unexpected driver failures.
            logger.warning(
                "dependency_unavailable",
                extra={"dependency": name, "error_type": type(exc).__name__},
            )
            states[name] = "unavailable"
    healthy = all(value == "ok" for value in states.values())
    response.status_code = 200 if healthy else 503
    response.headers["Cache-Control"] = "no-store"
    return ReadinessResponse(
        status="ready" if healthy else "not_ready",
        dependencies=Dependencies(database=states["database"], redis=states["redis"]),
    )
