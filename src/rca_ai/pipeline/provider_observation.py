"""Content-free timing events around provider operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable


class ObservedProvider:
    """Report provider start, completion, or failure without exposing request data."""

    def __init__(self, provider: Any, on_event: Callable[[str, Any | None], None]) -> None:
        self._provider = provider
        self._on_event = on_event

    def complete(self, request: Mapping[str, Any]) -> Any:
        self._on_event("provider_started", None)
        try:
            result = self._provider.complete(request)
        except Exception as error:
            self._on_event("provider_failed", error)
            raise
        self._on_event("provider_completed", result)
        return result
