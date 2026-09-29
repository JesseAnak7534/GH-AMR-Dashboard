"""Configuration reading.

The KoboToolbox token was read into a module constant at import time, so it was
found only when something else had already loaded .env, and never on Streamlit
Cloud where secrets are not environment variables.
"""

import os

import pytest

from src import settings


def test_environment_value_is_found():
    os.environ["ICBB_TEST_SETTING"] = "present"
    try:
        assert settings.get_setting("ICBB_TEST_SETTING") == "present"
    finally:
        os.environ.pop("ICBB_TEST_SETTING", None)


def test_missing_value_returns_the_default():
    assert settings.get_setting("ICBB_DEFINITELY_ABSENT") is None
    assert settings.get_setting("ICBB_DEFINITELY_ABSENT", "fallback") == "fallback"


def test_values_are_read_lazily_not_at_import():
    """A value set after import must still be found, which a module constant
    assigned at import time would miss."""
    assert settings.get_setting("ICBB_SET_LATE") is None
    os.environ["ICBB_SET_LATE"] = "appeared"
    try:
        assert settings.get_setting("ICBB_SET_LATE") == "appeared"
    finally:
        os.environ.pop("ICBB_SET_LATE", None)


def test_blank_is_treated_as_absent():
    os.environ["ICBB_BLANK"] = "   "
    try:
        assert settings.get_setting("ICBB_BLANK", "fallback") == "fallback"
    finally:
        os.environ.pop("ICBB_BLANK", None)


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("anything", False),
])
def test_boolean_settings(value, expected):
    os.environ["ICBB_FLAG"] = value
    try:
        assert settings.get_bool("ICBB_FLAG") is expected
    finally:
        os.environ.pop("ICBB_FLAG", None)


def test_unparseable_integer_falls_back():
    os.environ["ICBB_NUMBER"] = "not a number"
    try:
        assert settings.get_int("ICBB_NUMBER", 42) == 42
    finally:
        os.environ.pop("ICBB_NUMBER", None)


def test_kobo_token_does_not_depend_on_import_order():
    """The reported bug: the manager found no token although .env held one."""
    from src.lab_management import KoboToolboxManager
    manager = KoboToolboxManager()
    if settings.get_setting("KOBO_API_TOKEN"):
        assert manager.api_token, (
            "a configured token must be visible to the manager")


def test_env_file_is_anchored_to_the_project_root():
    """The bug behind "KoboToolbox API token is not configured".

    load_dotenv() with no argument searches upward from the current working
    directory. Launching Streamlit from anywhere other than the project root
    meant .env was never found, and every value in it silently did not exist.
    """
    import os

    from src import settings

    assert settings.ENV_FILE.endswith(".env")
    assert os.path.isabs(settings.ENV_FILE), (
        "the .env path must be absolute, not relative to the working directory")
    assert os.path.dirname(settings.ENV_FILE) == settings.PROJECT_ROOT


def test_no_module_loads_dotenv_from_the_working_directory():
    """Every module must go through src.settings.

    Six modules called a bare load_dotenv(). Each was a separate chance for
    configuration to vanish depending on where the process was started.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in list((root / "src").glob("*.py")) + [root / "app.py"]:
        if path.name == "settings.py":
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*load_dotenv\(\s*\)", line):
                offenders.append(f"{path.name}:{number}")
    assert not offenders, (
        "these call load_dotenv() with no path, which depends on the working "
        "directory: " + ", ".join(offenders))
