import os
from pathlib import Path

import pytest

# Test configuration only; deployments never receive a fallback pepper.
os.environ.setdefault("REDEMPTION_CODE_PEPPER", "test-suite-only-secret-do-not-use-in-a-deployment")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--pretrained", action="store_true", help="Require installed reviewed pretrained weights"
    )
    parser.addoption(
        "--pretrained-root",
        default="private-data/pretrained",
        help="Verified weight installation directory",
    )
    parser.addoption("--integration", action="store_true", help="Run real PostgreSQL/Redis checks")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--pretrained"):
        for item in items:
            if "pretrained" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(reason="Use --pretrained with reviewed installed weights")
                )
    if config.getoption("--integration"):
        return
    skip = pytest.mark.skip(reason="Start Compose and use --integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def pretrained_root(request: pytest.FixtureRequest) -> Path:
    from aevyra_inference.extractors import verified_weights

    root = (request.config.rootpath / request.config.getoption("--pretrained-root")).resolve()
    verified_weights(root)  # Missing/corrupt weights fail an explicitly requested test run.
    return root
