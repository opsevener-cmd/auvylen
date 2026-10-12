from unittest.mock import patch

import pytest
from aevyra_api.config import Settings
from aevyra_api.database import DependencyChecks


def test_database_probe_executes_sql() -> None:
    with patch("aevyra_api.database.build_engine") as build:
        checks = DependencyChecks(Settings(_env_file=None))
        checks.database()
        connection = build.return_value.connect.return_value.__enter__.return_value
        assert str(connection.execute.call_args.args[0]) == "SELECT 1"
        checks.close()
        build.return_value.dispose.assert_called_once()


def test_redis_probe_checks_ping() -> None:
    checks = DependencyChecks(Settings(_env_file=None))
    try:
        with patch.object(checks.redis, "ping", return_value=True) as ping:
            checks.cache()
            ping.assert_called_once()
        with patch.object(checks.redis, "ping", return_value=False):
            with pytest.raises(ConnectionError):
                checks.cache()
    finally:
        checks.close()


@pytest.mark.integration
def test_real_database() -> None:
    checks = DependencyChecks(Settings())
    try:
        checks.database()
    finally:
        checks.close()


@pytest.mark.integration
def test_real_redis() -> None:
    checks = DependencyChecks(Settings())
    try:
        checks.cache()
    finally:
        checks.close()
