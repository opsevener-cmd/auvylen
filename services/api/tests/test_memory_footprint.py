"""Startup import footprint, bounded password hashing and worker memory release."""

import os
import secrets
import subprocess
import sys
import threading
import time

from aevyra_api.accounts import ARGON2_CONCURRENCY, HASHER, BoundedHasher
from aevyra_api.research.worker import release_memory
from argon2 import PasswordHasher


def test_api_startup_does_not_import_numerical_runtimes() -> None:
    # A fresh interpreter: the test session itself has already imported numpy.
    env = {
        **os.environ,
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+psycopg://user:password@127.0.0.1:1/unused",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "REDEMPTION_CODE_PEPPER": secrets.token_hex(48),
        "CORS_ORIGINS": "[]",
    }
    code = (
        "import sys, aevyra_api.main\n"
        "heavy = [m for m in ('numpy', 'onnxruntime', 'scipy', 'torch') if m in sys.modules]\n"
        "print(','.join(heavy))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == ""


def test_password_hashing_concurrency_is_bounded() -> None:
    assert isinstance(HASHER, BoundedHasher)
    assert ARGON2_CONCURRENCY == 2
    active = peak = 0
    lock = threading.Lock()

    class Recording(PasswordHasher):
        def hash(self, password: str | bytes, *, salt: bytes | None = None) -> str:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return "hashed"

    bounded = BoundedHasher(Recording(), 2)
    threads = [threading.Thread(target=bounded.hash, args=("pw",)) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak == 2


def test_bounded_hasher_keeps_argon2_behaviour() -> None:
    hashed = HASHER.hash("test-only-password-1234")
    assert hashed.startswith("$argon2id$")
    assert HASHER.verify(hashed, "test-only-password-1234")
    assert not HASHER.check_needs_rehash(hashed)


def test_release_memory_is_safe_to_call_repeatedly() -> None:
    release_memory()
    release_memory()
