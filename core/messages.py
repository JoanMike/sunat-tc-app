"""Spanish user-facing message mapping for `FetchError` kinds.

Shared by the CLI and the GUI. Adding a new `FetchError.kind` without
extending `_FETCH_ERROR_MESSAGES_ES` is a localization spec violation
(it would surface as English debug text via the generic fallback).
"""
from __future__ import annotations

from .errors import FetchError

# Mapping from `FetchError.kind` to a Spanish user-facing message.
# `input` should not normally reach this point (validators run before
# `fetch_*`), but it is included for completeness so the mapping covers
# every kind the data layer can raise.
_FETCH_ERROR_MESSAGES_ES: dict[str, str] = {
    "network": (
        "No se pudo conectar con el servicio de SUNAT. Verifique su conexión "
        "a internet e intente de nuevo."
    ),
    "http_4xx": "La consulta fue rechazada por el servicio de SUNAT (HTTP {status}).",
    "http_5xx": (
        "El servicio de SUNAT no está disponible en este momento (HTTP "
        "{status}). Intente de nuevo más tarde."
    ),
    "parse": "El servicio de SUNAT devolvió una respuesta inesperada. Intente de nuevo más tarde.",
    "rate_limit": (
        "Demasiadas solicitudes al servicio de SUNAT. Espere un momento e "
        "intente de nuevo."
    ),
    "auth": (
        "La API rechazó el token configurado (inválido, vencido o sin cuota). "
        "Verifíquelo en «Configurar token…» e intente de nuevo."
    ),
    "input": "Parámetros de consulta inválidos.",
}

_GENERIC_FALLBACK = (
    "Error al consultar el tipo de cambio. Intente de nuevo más tarde."
)


def format_fetch_error(exc: FetchError) -> str:
    """Map a `FetchError` to a Spanish user-facing message.

    Includes the HTTP status for the `http_*xx` kinds when available so
    the user can debug intermittent failures without exposing the raw
    English-y exception text. An unknown kind returns a generic Spanish
    fallback (NEVER `str(exc)`).
    """
    template = _FETCH_ERROR_MESSAGES_ES.get(exc.kind, _GENERIC_FALLBACK)
    if exc.kind in ("http_4xx", "http_5xx") and exc.status is not None:
        return template.format(status=exc.status)
    return template
