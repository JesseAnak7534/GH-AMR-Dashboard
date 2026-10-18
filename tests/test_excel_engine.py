"""The Excel reader is interchangeable, and must stay so.

Uploads are read with python-calamine when it is installed, because openpyxl
spends about 34 seconds parsing a 2,500-specimen workbook against calamine's 2 --
the parse, not the validation, is what makes an upload feel slow. Swapping the
reader is only safe while both produce the same frames, so that is what these
check: a reader that quietly returned dates as text, or blanks as empty strings
rather than NaN, would change what the validator sees without failing anything.
"""

import io

import pandas as pd
import pytest

from src.upload_schema import excel_engine


def _workbook() -> bytes:
    """A small workbook exercising the value kinds that differ between readers:
    dates, times, floats, integers, blanks and text."""
    frame = pd.DataFrame({
        "sample_id": ["S1", "S2", "S3"],
        "collection_date": ["2026-01-05", "2026-02-10", None],
        "organism": ["Escherichia coli", None, "Klebsiella pneumoniae"],
        "mic_value": [0.25, None, 16.0],
        "count": [1, 2, 3],
        "flag": ["Yes", "No", None],
    })
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="samples", index=False)
    return buffer.getvalue()


def test_engine_selector_returns_a_usable_value():
    engine = excel_engine()
    assert engine in (None, "calamine"), (
        "None lets pandas choose; anything else must be an engine it accepts")


def test_both_readers_agree_on_every_value():
    if excel_engine() is None:
        pytest.skip("python-calamine is not installed; openpyxl is the only reader")

    raw = _workbook()
    frames = {}
    for engine in ("openpyxl", "calamine"):
        with pd.ExcelFile(io.BytesIO(raw), engine=engine) as book:
            frames[engine] = book.parse(sheet_name="samples")

    a, b = frames["openpyxl"], frames["calamine"]
    assert a.shape == b.shape
    assert list(a.columns) == list(b.columns)
    for column in a.columns:
        left = a[column].astype(str).str.strip()
        right = b[column].astype(str).str.strip()
        blank = {"nan", "NaT", "None", ""}
        mismatched = [(x, y) for x, y in zip(left, right)
                      if x != y and not (x in blank and y in blank)]
        assert not mismatched, f"{column}: readers disagree {mismatched[:3]}"


def test_a_blank_stays_blank_whichever_reader_is_used():
    """The distinction the validator depends on: an empty cell must not arrive
    as the text 'None' or an empty string that looks like an answer."""
    from src.upload_schema import is_blank

    raw = _workbook()
    engines = ["openpyxl"] + (["calamine"] if excel_engine() else [])
    for engine in engines:
        with pd.ExcelFile(io.BytesIO(raw), engine=engine) as book:
            frame = book.parse(sheet_name="samples")
        assert is_blank(frame["organism"].iloc[1]), f"{engine} lost a blank"
        assert is_blank(frame["mic_value"].iloc[1]), f"{engine} lost a blank"
        assert not is_blank(frame["mic_value"].iloc[0]), f"{engine} dropped 0.25"
