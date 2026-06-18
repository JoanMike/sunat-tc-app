"""Unit tests for `core.messages.format_fetch_error` (T2.1, Q4 / localization R1).

These tests assert the Spanish mapping table covers every FetchError.kind
value the data layer can raise and that the `http_*xx` kinds substitute
their HTTP status into the message template. They are written BEFORE
`core/messages.py` is created (T2.2) so they fail with ImportError.
"""
from __future__ import annotations

from core import FetchError, format_fetch_error

# ---------------------------------------------------------------------------
# Mapping coverage (every FetchError.kind has a Spanish mapping)
# ---------------------------------------------------------------------------


def test_format_fetch_error_network():
    """kind='network' must map to a Spanish connectivity message."""
    exc = FetchError(kind="network", message="boom")
    out = format_fetch_error(exc)
    assert out, "format_fetch_error must return a non-empty string"
    # Marker: any of these Spanish markers confirms we are NOT falling
    # back to raw str(exc) which would be the English "boom".
    assert any(
        marker in out.lower()
        for marker in ("conexi", "sunat", "intente", "verifique")
    ), f"expected a Spanish connectivity message, got {out!r}"
    assert "boom" not in out, f"format_fetch_error must NOT echo raw str(exc); got {out!r}"


def test_format_fetch_error_http_4xx_substitutes_status():
    """kind='http_4xx' must interpolate the HTTP status into the template."""
    exc = FetchError(kind="http_4xx", message="HTTP 404", status=404)
    out = format_fetch_error(exc)
    assert out, "format_fetch_error must return a non-empty string"
    assert "404" in out, f"http_4xx message must include the status 404; got {out!r}"
    assert any(
        marker in out.lower()
        for marker in ("sunat", "rechaz", "http", "intente")
    ), f"expected a friendly Spanish http_4xx message; got {out!r}"


def test_format_fetch_error_http_5xx_substitutes_status():
    """kind='http_5xx' must interpolate the HTTP status into the template."""
    exc = FetchError(kind="http_5xx", message="HTTP 503", status=503)
    out = format_fetch_error(exc)
    assert out, "format_fetch_error must return a non-empty string"
    assert "503" in out, f"http_5xx message must include the status 503; got {out!r}"
    assert any(
        marker in out.lower()
        for marker in ("sunat", "disponible", "intente", "http")
    ), f"expected a friendly Spanish http_5xx message; got {out!r}"


def test_format_fetch_error_parse():
    """kind='parse' must map to a Spanish 'unexpected response' message."""
    exc = FetchError(kind="parse", message="bad json")
    out = format_fetch_error(exc)
    assert out, "format_fetch_error must return a non-empty string"
    assert any(
        marker in out.lower()
        for marker in ("inesperada", "respuesta", "sunat", "intente")
    ), f"expected a Spanish 'unexpected response' message; got {out!r}"


def test_format_fetch_error_rate_limit():
    """kind='rate_limit' must map to a Spanish 'too many requests' message."""
    exc = FetchError(kind="rate_limit", message="HTTP 429", status=429)
    out = format_fetch_error(exc)
    assert out, "format_fetch_error must return a non-empty string"
    assert any(
        marker in out.lower()
        for marker in ("demasiadas", "solicitudes", "espere", "intente")
    ), f"expected a Spanish rate-limit message; got {out!r}"


def test_format_fetch_error_input():
    """kind='input' must map to a Spanish 'invalid parameters' message."""
    exc = FetchError(kind="input", message="bad arg")
    out = format_fetch_error(exc)
    assert out, "format_fetch_error must return a non-empty string"
    assert any(
        marker in out.lower()
        for marker in ("inv", "parámetros", "consulta", "parámetr")
    ), f"expected a Spanish invalid-params message; got {out!r}"


def test_format_fetch_error_unknown_kind_fallback():
    """An unknown kind MUST return a non-empty Spanish fallback (NOT str(exc)).

    Constructs the instance via `__new__` to bypass the Q2 kind-validation
    guard in `__init__`, so the `_GENERIC_FALLBACK` branch in
    `format_fetch_error` stays covered (defense-in-depth for kinds added
    without a matching message key, or paths that bypass `__init__` such as
    pickle / `__new__` reconstruction).
    """
    exc = FetchError.__new__(FetchError)
    exc.kind = "alien_invasion"
    exc.status = None
    Exception.__init__(exc, "raw text")
    out = format_fetch_error(exc)
    assert out, "fallback message must be non-empty"
    assert "raw text" not in out, (
        "fallback must not echo raw str(exc); got "
        f"{out!r}"
    )
    assert any(
        marker in out.lower()
        for marker in ("tipo de cambio", "intente", "consulta")
    ), f"expected a Spanish generic fallback; got {out!r}"
