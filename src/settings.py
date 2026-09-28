"""
One way to read configuration.

The platform reads settings from three places -- the process environment, a local
``.env`` file, and Streamlit Cloud's secrets store -- and had three different
conventions for doing it.

``src.db`` called ``load_dotenv()`` and then checked Streamlit secrets as a
fallback. ``src.email_utils`` checked secrets first and the environment second.
``src.lab_management`` did neither: it read ``os.getenv("KOBO_API_TOKEN")`` into
a module constant at import time.

That last one fails twice over. Reading at import time means the value depends
on whether something else has already loaded ``.env`` -- it worked only because
``src.db`` happens to be imported first and loads it as a side effect, so the
KoboToolbox sync worked or not according to import order. And reading only the
environment means the token can never be found on Streamlit Cloud, where secrets
are not environment variables. The reported error, "KoboToolbox API token is not
configured", was that: the token was present in ``.env`` and the code could not
see it.

This module is the single answer. It loads ``.env`` once on import, and
``get_setting`` reads lazily, at the moment a value is needed, from the
environment first and Streamlit secrets second.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Populate the environment from .env once, here, so no other module has to
# remember to and no module's behaviour depends on import order.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:                                     # noqa: BLE001
    logger.debug("python-dotenv unavailable or no .env file; "
                 "reading the environment directly")


def get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return a configuration value, or ``default``.

    Checked in order: the process environment (which includes anything loaded
    from ``.env``), then Streamlit secrets. Read at call time rather than import
    time, so a value that appears later -- a secret injected by the host, an
    environment variable set by a test -- is still found.

    Streamlit secrets raise rather than return empty when no secrets file
    exists, which is normal outside Streamlit Cloud, so that is caught.
    """
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()

    try:
        import streamlit as st
        secrets = getattr(st, "secrets", None)
        if secrets is not None and name in secrets:
            found = str(secrets[name]).strip()
            if found:
                return found
    except Exception:                                 # noqa: BLE001
        pass

    return default


def get_bool(name: str, default: bool = False) -> bool:
    """A setting read as a flag."""
    value = get_setting(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def get_int(name: str, default: int) -> int:
    """A setting read as a whole number, falling back when unparseable."""
    value = get_setting(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("%s is not a whole number (%r); using %s",
                       name, value, default)
        return default


def is_configured(name: str) -> bool:
    return bool(get_setting(name))


__all__ = ["get_setting", "get_bool", "get_int", "is_configured"]
