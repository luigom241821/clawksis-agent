"""Upstream adapter registry for the local proxy server (see :class:`UpstreamAdapter`)."""

from clawk_cli.proxy.adapters.base import UpstreamAdapter
from clawk_cli.proxy.adapters.xai import XAIGrokAdapter

# Keyed by the ``clawk proxy start --provider <name>`` value.
ADAPTERS: dict[str, type[UpstreamAdapter]] = {
    "xai": XAIGrokAdapter,
}


def get_adapter(name: str) -> UpstreamAdapter:
    """Instantiate an adapter by provider name."""
    key = (name or "").strip().lower()
    if key not in ADAPTERS:
        available = ", ".join(sorted(ADAPTERS)) or "(none)"
        raise ValueError(
            f"Unknown proxy upstream provider: {name!r}. Available: {available}"
        )
    return ADAPTERS[key]()


__all__ = ["ADAPTERS", "UpstreamAdapter", "get_adapter"]
