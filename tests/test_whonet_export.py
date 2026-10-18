"""The WHONET Excel export, at the widths a real export reaches.

A WHONET file carries one column per antibiotic, so it passes 52 columns
easily. The width-setting loop built its column letters by arithmetic on chr():
correct to 'AZ' and wrong after it. Column 53 produced 'A[' -- the character
after 'Z' in ASCII -- and openpyxl rejected the export, which the page then
reported as "Excel export requires openpyxl", sending anyone reading it to look
for an install problem that did not exist.

Columns 54 to 78 were the quieter half: they produced names like 'At', which
openpyxl accepts and which refer to a different column, so widths were applied
to the wrong ones with nothing raised at all.
"""

import io

import pandas as pd
import pytest
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from src.whonet import export_to_whonet_excel


def _frame(columns: int) -> pd.DataFrame:
    data = {f"AB_{i:03d}": ["S", "R", None] for i in range(1, columns + 1)}
    data["ORGANISM"] = ["Escherichia coli"] * 3
    data["SPEC_DATE"] = ["2026-01-01"] * 3
    return pd.DataFrame(data)


@pytest.mark.parametrize("columns", [1, 25, 26, 27, 51, 52, 53, 54, 78, 79, 120])
def test_export_survives_every_column_count(columns):
    """53 was the first that raised; 54-78 were wrong without raising."""
    frame = _frame(columns)
    payload = export_to_whonet_excel(frame)
    assert payload, "export produced no bytes"
    sheet = load_workbook(io.BytesIO(payload))["WHONET_Data"]
    assert sheet.max_column == len(frame.columns)


def test_widths_are_set_on_the_right_columns():
    """The silent half of the bug: a valid letter for the wrong column."""
    frame = _frame(80)
    sheet = load_workbook(io.BytesIO(export_to_whonet_excel(frame)))["WHONET_Data"]
    for index in range(1, len(frame.columns) + 1):
        letter = get_column_letter(index)
        assert letter in sheet.column_dimensions, (
            f"column {index} ({letter}) has no width set")
        assert sheet.column_dimensions[letter].width, f"{letter} width is zero"


def test_no_column_letter_contains_punctuation():
    """'A[' is the shape of the original failure."""
    frame = _frame(120)
    sheet = load_workbook(io.BytesIO(export_to_whonet_excel(frame)))["WHONET_Data"]
    for key in sheet.column_dimensions:
        assert key.isalpha(), f"{key!r} is not a column name"


def test_an_empty_frame_exports_nothing_rather_than_failing():
    assert export_to_whonet_excel(pd.DataFrame()) == b""


def test_header_row_is_written():
    frame = _frame(60)
    sheet = load_workbook(io.BytesIO(export_to_whonet_excel(frame)))["WHONET_Data"]
    assert sheet.cell(row=1, column=1).value == "AB_001"
    assert sheet.max_row == len(frame) + 1
