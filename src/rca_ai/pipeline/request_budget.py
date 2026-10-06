"""Provider-boundary size guard for complete semantic requests.

The estimate is an internal conservative byte heuristic, not the provider's
tokenizer or a quota guarantee. Guarding here ensures rejected requests never
reach the underlying transport and accepted requests are forwarded unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


DEFAULT_MAX_ESTIMATED_TOKENS = 7_000


class RequestBudgetExceeded(ValueError):
    """A complete serialized request exceeds the configured internal estimate."""

    def __init__(self, request_bytes: int, estimated_tokens: int, max_estimated_tokens: int) -> None:
        self.request_bytes = request_bytes
        self.estimated_tokens = estimated_tokens
        self.max_estimated_tokens = max_estimated_tokens
        super().__init__(
            "Complete request exceeds internal estimated-token budget "
            f"({estimated_tokens} estimated tokens from {request_bytes} bytes; "
            f"limit {max_estimated_tokens}). This estimate is not an exact provider token count."
        )


def request_size(request: Mapping[str, Any]) -> tuple[int, int]:
    """Return compact UTF-8 JSON bytes and the internal ceil(bytes / 4) estimate."""

    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    size_bytes = len(encoded)
    return size_bytes, (size_bytes + 3) // 4


class BudgetGuardProvider:
    """Reject oversize complete requests before delegating to a provider."""

    def __init__(self, provider: Any, *, max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS) -> None:
        if isinstance(max_estimated_tokens, bool) or not isinstance(max_estimated_tokens, int) or max_estimated_tokens <= 0:
            raise ValueError("max_estimated_tokens must be a positive integer")
        self._provider = provider
        self.max_estimated_tokens = max_estimated_tokens

    def complete(self, request: Mapping[str, Any]) -> Any:
        size_bytes, estimated_tokens = request_size(request)
        if estimated_tokens > self.max_estimated_tokens:
            raise RequestBudgetExceeded(size_bytes, estimated_tokens, self.max_estimated_tokens)
        return self._provider.complete(request)
