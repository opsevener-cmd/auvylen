"""Renewal and cooperative cancellation for workers; trainers must check at each batch."""

import logging
import threading
from pathlib import Path
from types import TracebackType

from aevyra_api.research.jobs import JobLease, ResearchQueue

logger = logging.getLogger("aevyra.worker")
HEARTBEAT = Path("/tmp/auvylen-worker-heartbeat")


class LeaseHeartbeat:
    def __init__(self, queue: ResearchQueue, lease: JobLease):
        self.queue = queue
        self.lease = lease
        self.stopping = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stopping.wait(min(5.0, self.queue.settings.job_lease_seconds / 3)):
            try:
                if not self.queue.renew(self.lease):
                    self.lost.set()
                    return
                HEARTBEAT.touch(mode=0o600)
            except Exception as exc:
                self.lost.set()
                logger.error(
                    "research_lease_renewal_failed", extra={"error_type": type(exc).__name__}
                )
                return

    def check(self) -> None:
        if self.lost.is_set():
            raise RuntimeError("Research lease no longer owned")

    def __enter__(self) -> "LeaseHeartbeat":
        self.thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stopping.set()
        self.thread.join()
