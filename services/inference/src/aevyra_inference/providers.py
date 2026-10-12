"""Independent optional providers. Discovery never downloads code or weights."""

import logging
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Protocol

from aevyra_inference.engine import ScoringEngine

logger = logging.getLogger("aevyra.providers")
PROVIDERS = {
    "custom": "Custom preference model",
    "comboloss": "ComboLoss",
    "fpem": "FPEM",
    "faclip": "FACLIP",
    "swingfvqa-ca": "SwinGFVQA-ca",
}


@dataclass(frozen=True)
class ProviderStatus:
    slug: str
    display_name: str
    available: bool
    reason: str


class ModelProvider(Protocol):
    """A plugin checks its dependencies, provenance and checkpoint before loading."""

    def availability(self, model_root: Path) -> ProviderStatus: ...

    def load(self, model_root: Path) -> ScoringEngine: ...


class ProviderCatalog:
    def __init__(self, enabled: list[str], model_root: Path) -> None:
        if any(slug not in PROVIDERS for slug in enabled):
            raise ValueError("Unknown model provider")
        self.enabled = set(enabled)
        self.model_root = model_root

    def _plugin(self, slug: str) -> ModelProvider | None:
        plugins = list(entry_points(group="auvylen.model_providers", name=slug))
        if len(plugins) != 1:
            return None
        factory = plugins[0].load()
        provider: ModelProvider = factory()
        return provider

    def status(self, slug: str) -> ProviderStatus:
        if slug not in self.enabled:
            return ProviderStatus(slug, PROVIDERS[slug], False, "disabled")
        try:
            plugin = self._plugin(slug)
            if plugin is None:
                return ProviderStatus(slug, PROVIDERS[slug], False, "adapter_not_installed")
            status = plugin.availability(self.model_root / slug)
            if status.slug != slug:
                raise ValueError("Provider identity mismatch")
            reason = (
                status.reason
                if status.reason
                in {"ready", "missing_weights", "missing_dependencies", "unreviewed_license"}
                else "dependency_or_configuration_error"
            )
            return ProviderStatus(slug, PROVIDERS[slug], status.available, reason)
        except Exception as exc:
            logger.error("provider_unavailable", extra={"error_type": type(exc).__name__})
            return ProviderStatus(slug, PROVIDERS[slug], False, "dependency_or_configuration_error")

    def statuses(self) -> list[ProviderStatus]:
        return [self.status(slug) for slug in PROVIDERS]

    def load(self, slug: str) -> ScoringEngine:
        if not self.status(slug).available:
            raise RuntimeError("Model provider unavailable")
        plugin = self._plugin(slug)
        if plugin is None:
            raise RuntimeError("Model provider unavailable")
        return plugin.load(self.model_root / slug)
