import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Deliberately omit exception text, request bodies, headers and connection URLs.
        exception_type = (
            record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else None
        )
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "service": "aevyra-api",
                "logger": record.name,
                "event": "server_exception" if record.exc_info else record.getMessage(),
                "request_id": request_id_context.get() or getattr(record, "request_id", None),
                "user_id": getattr(record, "user_id", None),
                "analysis_id": getattr(record, "analysis_id", None),
                "order_id": getattr(record, "order_id", None),
                "dependency": getattr(record, "dependency", None),
                "status_code": getattr(record, "status_code", None),
                "error_type": getattr(record, "error_type", exception_type),
            }
        )


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("aevyra")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    # Starlette re-raises handled unexpected errors to the server. Preserve the safe
    # error class, not Uvicorn's default traceback/exception text.
    server_logger = logging.getLogger("uvicorn.error")
    server_logger.handlers = [handler]
    server_logger.setLevel(level)
    server_logger.propagate = False
