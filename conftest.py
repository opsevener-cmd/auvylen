import os

import pytest

# Test configuration only; deployments never receive a fallback pepper.
os.environ.setdefault("REDEMPTION_CODE_PEPPER", "test-suite-only-secret-do-not-use-in-a-deployment")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--integration", action="store_true", help="Run real PostgreSQL/Redis checks")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--integration"):
        return
    skip = pytest.mark.skip(reason="Start Compose and use --integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
