"""Typed error for data-fetch failures.

Carries a `kind` discriminator so callers (CLI / GUI worker) can map to
user-facing messages without re-parsing exception text.
"""
from __future__ import annotations


class FetchError(Exception):
    """Raised by core fetch helpers on persistent or non-retryable failures.

    `kind` ∈ {"network", "http_4xx", "http_5xx", "parse", "rate_limit", "input"}.
    """

    kinds = ("network", "http_4xx", "http_5xx", "parse", "rate_limit", "input")

    def __init__(self, kind: str, message: str = "", *, status: int | None = None) -> None:
        super().__init__(message or kind)
        self.kind = kind
        self.status = status
