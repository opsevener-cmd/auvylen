"""CPU worker now; a separately deployed worker can select the gpu queue later."""

import logging
import signal
import time
from pathlib import Path

from aevyra_inference.engine import EngineRegistry
from aevyra_inference.mock import MockScoringEngine

from aevyra_api.config import Settings
from aevyra_api.database import DependencyChecks
from aevyra_api.logging import configure_logging
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.lease import LeaseHeartbeat

logger = logging.getLogger("aevyra.worker")
HEARTBEAT = Path("/tmp/auvylen-worker-heartbeat")


def run_one(queue: ResearchQueue) -> bool:
    lease = queue.claim()
    if lease is None:
        return False
    try:
        with LeaseHeartbeat(queue, lease) as heartbeat:
            if lease.kind != "SCORE" or lease.provider != "mock":
                raise RuntimeError("Requested model or training implementation unavailable")
            score = EngineRegistry([MockScoringEngine()]).score(
                "mock",
                f"auvylen-research:{lease.id}".encode(),
                production=queue.settings.api_environment == "production",
            )
            heartbeat.check()
            if queue.finish(lease, score.model_dump(mode="json")):
                logger.info("research_job_finished", extra={"analysis_id": str(lease.id)})
    except Exception as exc:
        queue.finish(lease, None)
        logger.error("research_job_failed", extra={"error_type": type(exc).__name__})
    return True


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    if not settings.research_mode:
        raise SystemExit("Worker requires explicit RESEARCH_MODE=true")
    checks = DependencyChecks(settings)
    queue = ResearchQueue(checks.sessions, settings)
    stopping = False
    last_cleanup = 0.0

    def stop(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            try:
                checks.database()
                checks.cache()
                if time.monotonic() - last_cleanup >= 60:
                    PreferenceService(checks.sessions, settings).purge()
                    last_cleanup = time.monotonic()
                run_one(queue)
                HEARTBEAT.touch(mode=0o600)
            except Exception as exc:
                logger.error("worker_dependency_failure", extra={"error_type": type(exc).__name__})
            time.sleep(1)
    finally:
        checks.close()


if __name__ == "__main__":
    main()
