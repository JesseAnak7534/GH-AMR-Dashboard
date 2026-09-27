"""
Validation of uploaded AMR workbooks against the contract in ``upload_schema``.

What changed and why
--------------------
The previous validator cast every object column to ``str`` before testing for
missing values. After that cast a blank cell holds the string ``"nan"``, which
is not null, so the "missing values in required column" check could never fire
and empty identifiers were stored as the literal text ``nan``. Blank handling
now goes through ``upload_schema.is_blank`` and happens before any cast.

It also grouped ``ast_results`` on ``isolate_id`` + ``antibiotic`` to find
duplicates. Because the old format issued a fresh ``isolate_id`` for every
susceptibility test, that group was almost always of size one, so the check
passed on files where one culture had been recorded as six isolates. Isolates
are now a sheet of their own, and when a workbook does not supply one they are
derived by grouping on specimen and organism -- which is what those files meant.

Validation is in two tiers. An **error** blocks the upload: the row cannot be
stored without losing or corrupting meaning. A **warning** is recorded and
shown, and the upload proceeds: the data is usable but less informative than it
could be. Nothing is silently repaired.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from src.interpretation import interpret_ast_result, platform_breakpoint_label
from src.lab_management import get_lab_names
from src.traceability import STERILE_SITE_SPECIMENS, age_to_band
from src.upload_schema import (
    AST_SHEET,
    GENOMICS_SHEET,
    ISOLATES_SHEET,
    MANDATORY_SHEETS,
    RESULT_VALUES,
    SAMPLES_SHEET,
    SHEETS,
    SOURCE_CATEGORIES,
    Column,
    Sheet,
    clean_text,
    is_blank,
    parse_bool,
    parse_list,
)

# Legacy names kept so existing imports and messages do not change meaning.
VALID_SOURCE_CATEGORIES = set(SOURCE_CATEGORIES)
VALID_RESULTS = {"S", "I", "R"}
VALID_METHODS = {"DD", "MIC"}
VALID_GUIDELINES = {"CLSI", "EUCAST"}

REQUIRED_SAMPLES_COLUMNS = set(SAMPLES_SHEET.header_required_columns)
REQUIRED_AST_COLUMNS = set(AST_SHEET.header_required_columns)

#: A malformed file can break the same rule on every one of ten thousand rows.
#: Reporting the first few and a count is more useful than a wall of text.
MAX_ISSUES_PER_RULE = 8

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


# ---------------------------------------------------------------------------
# Issue reporting
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationIssue:
    sheet: str
    message: str
    severity: str = SEVERITY_ERROR
    row: Optional[int] = None       # Excel row number, header counted
    column: Optional[str] = None

    def render(self) -> str:
        where = self.sheet
        if self.row is not None:
            where += f" row {self.row}"
        if self.column:
            where += f", column {self.column}"
        return f"[{where}] {self.message}"


class _IssueLog:
    """Collects issues, capping repeats of the same rule."""

    def __init__(self) -> None:
        self._issues: List[ValidationIssue] = []
        self._counts: Dict[Tuple[str, str, str], int] = {}
        self._suppressed: Dict[Tuple[str, str, str], int] = {}

    def add(self, sheet: str, message: str, *, severity: str = SEVERITY_ERROR,
            row: Optional[int] = None, column: Optional[str] = None,
            rule: Optional[str] = None) -> None:
        key = (sheet, column or "", rule or message)
        seen = self._counts.get(key, 0)
        self._counts[key] = seen + 1
        if seen >= MAX_ISSUES_PER_RULE:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return
        self._issues.append(ValidationIssue(sheet=sheet, message=message,
                                            severity=severity, row=row,
                                            column=column))

    def finish(self) -> List[ValidationIssue]:
        """Return the issues, with one summary line per suppressed rule."""
        out = list(self._issues)
        for (sheet, column, rule), extra in sorted(self._suppressed.items()):
            out.append(ValidationIssue(
                sheet=sheet,
                column=column or None,
                severity=SEVERITY_WARNING,
                message=(f"{extra} further row(s) have the same problem "
                         f"({rule}). Fix the ones listed and re-upload to see "
                         "the rest."),
            ))
        return out


# ---------------------------------------------------------------------------
# Typed cell parsing
# ---------------------------------------------------------------------------

def _excel_row(index: int) -> int:
    """Map a zero-based dataframe index to the Excel row the user sees."""
    return int(index) + 2


def _parse_date(value) -> Tuple[Optional[_dt.date], Optional[str]]:
    """Parse a date cell. Returns (date, error message)."""
    if is_blank(value):
        return None, None
    if isinstance(value, _dt.datetime):
        return value.date(), None
    if isinstance(value, _dt.date):
        return value, None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date(), None
    text = str(value).strip()
    # Excel sometimes hands back a full timestamp for a date-formatted cell.
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return _dt.datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, (f"'{value}' is not a date in YYYY-MM-DD form. Day-first and "
                  "month-first formats are ambiguous, so they are not accepted.")


def _parse_time(value) -> Tuple[Optional[_dt.time], Optional[str]]:
    if is_blank(value):
        return None, None
    if isinstance(value, _dt.datetime):
        return value.time(), None
    if isinstance(value, _dt.time):
        return value, None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().time(), None
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return _dt.datetime.strptime(text, fmt).time(), None
        except ValueError:
            continue
    # A time-formatted Excel cell can arrive as a fraction of a day.
    try:
        fraction = float(text)
        if 0 <= fraction < 1:
            seconds = int(round(fraction * 86400))
            return (_dt.time(seconds // 3600, (seconds % 3600) // 60,
                             seconds % 60), None)
    except ValueError:
        pass
    return None, f"'{value}' is not a time in HH:MM form."


def _parse_number(value) -> Tuple[Optional[float], Optional[str]]:
    if is_blank(value):
        return None, None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None, f"'{value}' is not a number."
    if not np.isfinite(number):
        return None, f"'{value}' is not a finite number."
    return number, None


def _parse_integer(value) -> Tuple[Optional[int], Optional[str]]:
    number, error = _parse_number(value)
    if error or number is None:
        return None, error
    if abs(number - round(number)) > 1e-9:
        return None, f"'{value}' must be a whole number."
    return int(round(number)), None


def _combine(date_value: Optional[_dt.date],
             time_value: Optional[_dt.time]) -> Optional[str]:
    """Build an ISO timestamp from a date and an optional time.

    Midnight is used when no time was given. It is a real limitation -- a
    specimen collected at an unknown hour is stored as 00:00 -- but the
    alternative of dropping the date loses more.
    """
    if date_value is None:
        return None
    return _dt.datetime.combine(date_value, time_value or _dt.time()).isoformat()


# ---------------------------------------------------------------------------
# Frame normalisation
# ---------------------------------------------------------------------------

def _normalise_frame(df: pd.DataFrame, sheet: Sheet,
                     log: _IssueLog) -> pd.DataFrame:
    """Return a frame with contract columns present and blanks as None.

    Headers are stripped and matched case-insensitively. Unknown columns are
    kept out of the result and reported as a warning rather than dropped in
    silence, because a typo in a header is the most common reason a filled
    column appears empty.
    """
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]

    lowered = {c.lower(): c for c in out.columns}
    rename: Dict[str, str] = {}
    for col in sheet.columns:
        actual = lowered.get(col.name.lower())
        if actual and actual != col.name:
            rename[actual] = col.name
    if rename:
        out = out.rename(columns=rename)

    known = set(sheet.column_names)
    unknown = [c for c in out.columns if c not in known
               and not str(c).startswith("Unnamed:")]
    for name in unknown:
        log.add(sheet.name, f"Column '{name}' is not part of the upload "
                            "contract and was ignored. Check the spelling "
                            "against the Data dictionary sheet.",
                severity=SEVERITY_WARNING, column=name, rule="unknown-column")

    for col in sheet.columns:
        if col.name not in out.columns:
            out[col.name] = None

    out = out[list(sheet.column_names)]

    # Blank-normalise before anything casts. This is the fix for the "nan"
    # string: every emptiness spelling becomes None exactly once, here.
    for name in out.columns:
        out[name] = out[name].map(lambda v: None if is_blank(v) else v)

    # Drop rows that are entirely empty -- trailing blank rows are normal in a
    # spreadsheet and are not errors.
    out = out[~out.isna().all(axis=1)].reset_index(drop=True)
    return out


def _check_headers(df: pd.DataFrame, sheet: Sheet,
                   log: _IssueLog) -> Tuple[bool, Set[str]]:
    """Check the headers a sheet cannot work without.

    Returns whether the sheet is usable, and the set of contract columns whose
    header is absent. Sector-specific columns are not demanded here -- whether
    they are needed depends on the rows, so that check happens once the sector
    of each row is known.
    """
    present = {str(c).strip().lower() for c in df.columns}
    absent = {c.name for c in sheet.columns if c.name.lower() not in present}

    missing = [name for name in sheet.header_required_columns if name in absent]
    if missing:
        log.add(sheet.name,
                "Missing required column(s): " + ", ".join(sorted(missing)) +
                ". Download a fresh template if the file predates the current "
                "format.", rule="missing-headers")
    return (not missing), absent


def _check_conditional_headers(sheet: Sheet, absent: Set[str],
                               sectors_present: Set[str],
                               log: _IssueLog) -> Set[str]:
    """Demand a sector-specific column only when its sector is in the file.

    Returns the names already reported here, so the per-row checks can stay
    quiet about them rather than repeating the same fact once per row.
    """
    reported: Set[str] = set()
    for col in sheet.conditional_columns:
        if col.name not in absent:
            continue
        triggered = sorted(set(col.required_for_sectors) & sectors_present)
        if not triggered:
            continue
        log.add(sheet.name,
                f"The column '{col.name}' is missing, and the file contains "
                + ", ".join(triggered)
                + f" specimens, which require it. {col.description}",
                column=col.name, rule=f"missing-conditional:{col.name}")
        reported.add(col.name)
    return reported


def _validate_typed_cell(value, col: Column, sheet_name: str, row: int,
                         log: _IssueLog):
    """Check one cell against its column contract. Returns the parsed value."""
    if is_blank(value):
        return None

    if col.vocabulary is not None:
        text = str(value).strip()
        if text not in col.vocabulary:
            match = [v for v in col.vocabulary if v.lower() == text.lower()]
            if match:
                return match[0]
            log.add(sheet_name,
                    f"'{text}' is not an accepted value. Use one of: "
                    + ", ".join(col.vocabulary) + ".",
                    row=row, column=col.name, rule=f"vocab:{col.name}")
            return None
        return text

    if col.kind == "date":
        parsed, error = _parse_date(value)
    elif col.kind == "time":
        parsed, error = _parse_time(value)
    elif col.kind == "integer":
        parsed, error = _parse_integer(value)
    elif col.kind == "number":
        parsed, error = _parse_number(value)
    elif col.kind == "boolean":
        parsed = parse_bool(value)
        error = (None if parsed is not None else
                 f"'{value}' is not Yes or No.")
    elif col.kind == "list":
        return parse_list(value)
    else:
        return clean_text(value)

    if error:
        log.add(sheet_name, error, row=row, column=col.name,
                rule=f"type:{col.name}")
        return None

    if parsed is not None and col.kind in ("number", "integer"):
        if col.minimum is not None and parsed < col.minimum:
            log.add(sheet_name,
                    f"{parsed:g} is below the minimum of {col.minimum:g}.",
                    row=row, column=col.name, rule=f"min:{col.name}")
            return None
        if col.maximum is not None and parsed > col.maximum:
            log.add(sheet_name,
                    f"{parsed:g} is above the maximum of {col.maximum:g}.",
                    row=row, column=col.name, rule=f"max:{col.name}")
            return None

    return parsed


# ---------------------------------------------------------------------------
# Sheet-level validation
# ---------------------------------------------------------------------------

def _check_duplicate_keys(df: pd.DataFrame, sheet: Sheet,
                          log: _IssueLog) -> None:
    keys = [k for k in sheet.key_columns if k in df.columns]
    if not keys or df.empty:
        return
    subset = df[keys].astype(str)
    duplicated = subset.duplicated(keep=False)
    if not duplicated.any():
        return
    for value, group in df[duplicated].groupby(keys, dropna=False):
        rows = [_excel_row(i) for i in group.index]
        label = value if isinstance(value, tuple) else (value,)
        pairs = ", ".join(f"{k}={v}" for k, v in zip(keys, label))
        log.add(sheet.name,
                f"{pairs} appears on rows {rows}. Each combination must be "
                "unique within the sheet.", rule="duplicate-key")


def _validate_samples(df: pd.DataFrame, log: _IssueLog,
                      already_reported: Optional[Set[str]] = None) -> pd.DataFrame:
    """Validate the specimen sheet and return the parsed frame."""
    sheet = SAMPLES_SHEET
    already_reported = already_reported or set()
    parsed_rows: List[Dict[str, object]] = []
    approved_labs = {str(name).strip().lower(): str(name).strip()
                     for name in get_lab_names()}

    for index, raw in df.iterrows():
        row = _excel_row(index)
        record: Dict[str, object] = {}
        # Columns whose value was present but rejected. Such a cell is a
        # different problem from an empty one and must not be reported as both.
        rejected: Set[str] = set()

        category = clean_text(raw.get("source_category"))
        category_upper = (category or "").upper()
        if category is None:
            log.add(sheet.name, "source_category is required.",
                    row=row, column="source_category", rule="required")
        elif category_upper not in VALID_SOURCE_CATEGORIES:
            log.add(sheet.name,
                    f"'{category}' is not an accepted sector. Use one of: "
                    + ", ".join(sorted(VALID_SOURCE_CATEGORIES)) + ".",
                    row=row, column="source_category", rule="vocab:sector")
            category_upper = ""
        record["source_category"] = category_upper or None

        for col in sheet.columns:
            if col.name == "source_category":
                continue
            value = raw.get(col.name)

            if col.required and is_blank(value):
                log.add(sheet.name, f"{col.name} is required.",
                        row=row, column=col.name, rule="required")
                record[col.name] = None
                continue

            if (col.is_conditional and is_blank(value)
                    and category_upper in col.required_for_sectors):
                if col.name in already_reported:
                    record[col.name] = None
                    continue
                log.add(sheet.name,
                        f"{col.name} is required for {category_upper} "
                        f"specimens. {col.description}",
                        row=row, column=col.name, rule="required-for-sector")
                record[col.name] = None
                continue

            # A patient field on a non-human row is a data-entry mistake worth
            # naming: it usually means the sector column is wrong.
            if (not is_blank(value) and col.sectors
                    and category_upper and category_upper not in col.sectors):
                log.add(sheet.name,
                        f"{col.name} is only used for "
                        + ", ".join(col.sectors)
                        + f" specimens, but this row is {category_upper}. "
                          "The value was ignored.",
                        severity=SEVERITY_WARNING, row=row, column=col.name,
                        rule=f"sector-mismatch:{col.name}")
                record[col.name] = None
                continue

            record[col.name] = _validate_typed_cell(value, col, sheet.name,
                                                    row, log)
            if record[col.name] is None and not is_blank(value):
                rejected.add(col.name)

        lab = record.get("lab_name")
        if lab is not None and approved_labs:
            canonical = approved_labs.get(str(lab).strip().lower())
            if canonical is None:
                log.add(sheet.name,
                        f"'{lab}' is not an approved laboratory. Choose from "
                        "the dropdown on the samples sheet.",
                        row=row, column="lab_name", rule="unknown-lab")
            else:
                record["lab_name"] = canonical

        # -- cross-field rules -------------------------------------------
        collection = record.get("collection_date")
        receipt = record.get("receipt_date")
        if collection and receipt and receipt < collection:
            log.add(sheet.name,
                    f"receipt_date ({receipt}) precedes collection_date "
                    f"({collection}).", row=row, column="receipt_date",
                    rule="receipt-before-collection")

        admission = record.get("admission_date")
        discharge = record.get("discharge_date")
        if admission and discharge and discharge < admission:
            log.add(sheet.name,
                    f"discharge_date ({discharge}) precedes admission_date "
                    f"({admission}).", row=row, column="discharge_date",
                    rule="discharge-before-admission")
        if admission and collection and collection < admission:
            log.add(sheet.name,
                    f"collection_date ({collection}) precedes admission_date "
                    f"({admission}). One of the two is wrong, and infection "
                    "onset cannot be classified from them as they stand.",
                    row=row, column="collection_date",
                    rule="collection-before-admission")

        if (record.get("condition_on_receipt") == "Rejected"
                and not record.get("rejection_reason")):
            log.add(sheet.name,
                    "condition_on_receipt is Rejected, so rejection_reason is "
                    "required.", row=row, column="rejection_reason",
                    rule="rejection-needs-reason")

        if record.get("receipt_time") and not record.get("receipt_date"):
            log.add(sheet.name,
                    "receipt_time was given without receipt_date, so it "
                    "cannot be placed in time and was ignored.",
                    severity=SEVERITY_WARNING, row=row, column="receipt_time",
                    rule="time-without-date")
            record["receipt_time"] = None

        # -- derived fields ----------------------------------------------
        record["collection_datetime"] = _combine(record.get("collection_date"),
                                                 record.get("collection_time"))
        record["receipt_datetime"] = _combine(record.get("receipt_date"),
                                              record.get("receipt_time"))
        record["sector"] = (record["source_category"].lower()
                            if record.get("source_category") else None)
        record["age_band"] = (age_to_band(record.get("age_years"))
                              if category_upper == "HUMAN" else None)
        if not record.get("ward_type_at_collection"):
            record["ward_type_at_collection"] = record.get("ward_type")
        if not record.get("ward_at_collection"):
            record["ward_at_collection"] = record.get("ward")

        if category_upper == "HUMAN":
            for column, note, rule in (
                ("age_years",
                 "age_years is empty. Age-stratified reporting and paediatric "
                 "breakpoint review are not possible for this specimen.",
                 "missing-age"),
                ("sex", "sex is empty.", "missing-sex"),
                ("admission_date",
                 "admission_date is empty, so this specimen cannot be "
                 "classified as community-onset or healthcare-associated.",
                 "missing-admission"),
            ):
                if record.get(column) is None and column not in rejected:
                    log.add(sheet.name, note, severity=SEVERITY_WARNING,
                            row=row, column=column, rule=rule)

        parsed_rows.append(record)

    result = pd.DataFrame(parsed_rows) if parsed_rows else pd.DataFrame(
        columns=list(sheet.column_names) + ["collection_datetime",
                                            "receipt_datetime", "sector",
                                            "age_band"])
    _check_duplicate_keys(result, sheet, log)
    return result


def _validate_isolates(df: pd.DataFrame, sample_ids: Set[str],
                       log: _IssueLog) -> pd.DataFrame:
    sheet = ISOLATES_SHEET
    parsed_rows: List[Dict[str, object]] = []

    for index, raw in df.iterrows():
        row = _excel_row(index)
        record: Dict[str, object] = {}
        for col in sheet.columns:
            value = raw.get(col.name)
            if col.required and is_blank(value):
                log.add(sheet.name, f"{col.name} is required.", row=row,
                        column=col.name, rule="required")
                record[col.name] = None
                continue
            record[col.name] = _validate_typed_cell(value, col, sheet.name,
                                                    row, log)

        sample_id = record.get("sample_id")
        if sample_id and str(sample_id) not in sample_ids:
            log.add(sheet.name,
                    f"sample_id '{sample_id}' does not appear on the samples "
                    "sheet.", row=row, column="sample_id",
                    rule="orphan-sample")

        if record.get("isolate_number") is None:
            record["isolate_number"] = 1

        parsed_rows.append(record)

    result = pd.DataFrame(parsed_rows) if parsed_rows else pd.DataFrame(
        columns=list(sheet.column_names))
    _check_duplicate_keys(result, sheet, log)

    # Two isolates from one specimen cannot share a sequence number; the
    # database enforces this, and catching it here gives a row number.
    if not result.empty and {"sample_id", "isolate_number"} <= set(result.columns):
        pairs = result[["sample_id", "isolate_number"]].astype(str)
        for value, group in result[pairs.duplicated(keep=False)].groupby(
                ["sample_id", "isolate_number"], dropna=False):
            log.add(sheet.name,
                    f"specimen {value[0]} has more than one isolate numbered "
                    f"{value[1]} (rows {[_excel_row(i) for i in group.index]}). "
                    "Number the organisms recovered from one specimen 1, 2, 3.",
                    rule="duplicate-isolate-number")
    return result


def _validate_ast(df: pd.DataFrame, sample_ids: Set[str],
                  declared_isolate_ids: Optional[Set[str]],
                  isolate_organism: Dict[str, str],
                  log: _IssueLog,
                  already_reported: Optional[Set[str]] = None) -> pd.DataFrame:
    sheet = AST_SHEET
    already_reported = already_reported or set()
    parsed_rows: List[Dict[str, object]] = []

    for index, raw in df.iterrows():
        row = _excel_row(index)
        record: Dict[str, object] = {}
        for col in sheet.columns:
            value = raw.get(col.name)
            if col.required and is_blank(value):
                # A header-optional column is required by what the row holds,
                # not on its own, so its own cross-field rule reports it with
                # the reason attached. Reporting it twice helps nobody.
                if col.header_optional:
                    record[col.name] = None
                    continue
                log.add(sheet.name, f"{col.name} is required.", row=row,
                        column=col.name, rule="required")
                record[col.name] = None
                continue
            record[col.name] = _validate_typed_cell(value, col, sheet.name,
                                                    row, log)

        sample_id = record.get("sample_id")
        if sample_id and str(sample_id) not in sample_ids:
            log.add(sheet.name,
                    f"sample_id '{sample_id}' does not appear on the samples "
                    "sheet.", row=row, column="sample_id",
                    rule="orphan-sample")

        isolate_id = record.get("isolate_id")
        if isolate_id and declared_isolate_ids is not None:
            if str(isolate_id) not in declared_isolate_ids:
                log.add(sheet.name,
                        f"isolate_id '{isolate_id}' does not appear on the "
                        "isolates sheet.", row=row, column="isolate_id",
                        rule="orphan-isolate")
            else:
                # Only compare against an unambiguous declaration. A duplicated
                # isolate_id is already an error of its own; comparing against
                # whichever duplicate was read last would be misleading.
                declared = isolate_organism.get(str(isolate_id))
                organism = record.get("organism")
                if declared and organism and (
                        str(organism).strip().lower() != declared.strip().lower()):
                    log.add(sheet.name,
                            f"organism '{organism}' disagrees with the "
                            f"isolates sheet, which records '{declared}' for "
                            f"{isolate_id}. The isolates sheet is "
                            "authoritative.", severity=SEVERITY_WARNING,
                            row=row, column="organism",
                            rule="organism-disagreement")
                if declared:
                    record["organism"] = declared

        method = record.get("method")
        mic = record.get("mic_value")
        zone = record.get("zone_diameter")
        result_value = record.get("result")

        if method == "MIC" and mic is None and result_value is None:
            log.add(sheet.name,
                    "method is MIC but neither mic_value nor result was given, "
                    "so there is nothing to interpret or store.", row=row,
                    column="mic_value", rule="mic-without-value")
        if method == "DD" and zone is None and result_value is None:
            log.add(sheet.name,
                    "method is DD but neither zone_diameter nor result was "
                    "given.", row=row, column="zone_diameter",
                    rule="dd-without-zone")
        if method == "DD" and mic is not None and zone is None:
            log.add(sheet.name,
                    "method is DD but only an MIC was supplied. Set method to "
                    "MIC, or give the zone diameter.",
                    severity=SEVERITY_WARNING, row=row, column="method",
                    rule="method-value-mismatch")
        if method == "MIC" and zone is not None and mic is None:
            log.add(sheet.name,
                    "method is MIC but only a zone diameter was supplied. Set "
                    "method to DD, or give the MIC.",
                    severity=SEVERITY_WARNING, row=row, column="method",
                    rule="method-value-mismatch")
        if record.get("mic_operator") and mic is None:
            log.add(sheet.name,
                    "mic_operator was given without an mic_value.",
                    severity=SEVERITY_WARNING, row=row, column="mic_operator",
                    rule="operator-without-value")

        if (result_value is not None and not record.get("guideline_version")
                and "guideline_version" not in already_reported):
            log.add(sheet.name,
                    "result was given but guideline_version is empty. "
                    "Breakpoints change between editions, so an S/I/R with no "
                    "edition behind it cannot be reproduced or audited.",
                    row=row, column="guideline_version",
                    rule="result-without-version")

        if record.get("qc_status") == "Fail":
            log.add(sheet.name,
                    "quality control failed on this run. The result is stored "
                    "and flagged, and is excluded from cumulative reporting.",
                    severity=SEVERITY_WARNING, row=row, column="qc_status",
                    rule="qc-fail")

        parsed_rows.append(record)

    result = pd.DataFrame(parsed_rows) if parsed_rows else pd.DataFrame(
        columns=list(sheet.column_names))
    _check_duplicate_keys(result, sheet, log)
    return result


def _validate_genomics(df: pd.DataFrame, isolate_ids: Set[str],
                       log: _IssueLog) -> pd.DataFrame:
    sheet = GENOMICS_SHEET
    parsed_rows: List[Dict[str, object]] = []

    for index, raw in df.iterrows():
        row = _excel_row(index)
        record: Dict[str, object] = {}
        for col in sheet.columns:
            value = raw.get(col.name)
            if col.required and is_blank(value):
                log.add(sheet.name, f"{col.name} is required.", row=row,
                        column=col.name, rule="required")
                record[col.name] = None
                continue
            record[col.name] = _validate_typed_cell(value, col, sheet.name,
                                                    row, log)

        isolate_id = record.get("isolate_id")
        if isolate_id and str(isolate_id) not in isolate_ids:
            log.add(sheet.name,
                    f"isolate_id '{isolate_id}' does not appear in this "
                    "workbook. A genomic result must attach to an isolate, "
                    "otherwise it cannot be linked to a phenotype or a "
                    "patient.", row=row, column="isolate_id",
                    rule="orphan-isolate")

        if record.get("read_path") and not record.get("read_checksum"):
            log.add(sheet.name,
                    "read_path was given without read_checksum. A stored "
                    "pointer that cannot be verified is not reproducible "
                    "evidence.", row=row, column="read_checksum",
                    rule="reads-without-checksum")
        if record.get("assembly_path") and not record.get("assembly_checksum"):
            log.add(sheet.name,
                    "assembly_path was given without assembly_checksum.",
                    severity=SEVERITY_WARNING, row=row,
                    column="assembly_checksum",
                    rule="assembly-without-checksum")
        if record.get("review_status") == "Accepted" and not record.get("reviewed_by"):
            log.add(sheet.name,
                    "review_status is Accepted, so reviewed_by is required.",
                    row=row, column="reviewed_by", rule="accepted-needs-reviewer")
        genes = record.get("amr_genes") or []
        if genes and not record.get("amr_db_version"):
            log.add(sheet.name,
                    "resistance genes were reported without amr_db_version. A "
                    "gene call is only interpretable against the database "
                    "version that produced it.", severity=SEVERITY_WARNING,
                    row=row, column="amr_db_version", rule="genes-without-db")

        parsed_rows.append(record)

    result = pd.DataFrame(parsed_rows) if parsed_rows else pd.DataFrame(
        columns=list(sheet.column_names))
    _check_duplicate_keys(result, sheet, log)
    return result


# ---------------------------------------------------------------------------
# Isolate derivation for workbooks with no isolates sheet
# ---------------------------------------------------------------------------

def derive_isolates(ast_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Derive one isolate per (specimen, organism) from the AST rows.

    Returns the derived isolates frame and the AST frame with ``isolate_id``
    rewritten to point at them.

    This is the migration path for the old format, where ``isolate_id`` was
    issued per susceptibility test. Grouping on specimen and organism recovers
    what such a file meant: one culture, several drugs. It cannot recover a case
    where two colonies of the same species from one specimen were genuinely
    separate isolates -- that distinction was never recorded, and inventing one
    would be worse than collapsing them.
    """
    if ast_df.empty:
        return pd.DataFrame(columns=list(ISOLATES_SHEET.column_names)), ast_df

    working = ast_df.copy()
    working["_sample"] = working["sample_id"].astype(str)
    working["_organism"] = working["organism"].astype(str).str.strip()

    pairs = (working[["_sample", "_organism"]]
             .drop_duplicates()
             .sort_values(["_sample", "_organism"])
             .reset_index(drop=True))
    pairs["isolate_number"] = pairs.groupby("_sample").cumcount() + 1
    pairs["isolate_id"] = (pairs["_sample"] + "-"
                           + pairs["isolate_number"].astype(str))

    lookup = {(r["_sample"], r["_organism"]): r["isolate_id"]
              for _, r in pairs.iterrows()}

    working["isolate_id"] = [
        lookup[(s, o)] for s, o in zip(working["_sample"], working["_organism"])
    ]
    working = working.drop(columns=["_sample", "_organism"])

    isolates = pd.DataFrame({
        "sample_id": pairs["_sample"],
        "isolate_id": pairs["isolate_id"],
        "isolate_number": pairs["isolate_number"],
        "organism": pairs["_organism"],
        "organism_code": None,
        "identification_method": None,
        "identification_date": None,
        "is_significant": None,
        "notes": None,
    })
    return isolates, working


# ---------------------------------------------------------------------------
# Automated interpretation
# ---------------------------------------------------------------------------

def perform_automated_interpretation(ast_df: pd.DataFrame) -> pd.DataFrame:
    """Fill a blank ``result`` from the measurement, where a breakpoint exists.

    Three things the previous version got wrong are fixed here.

    The engine returns ``'Unknown'`` when it holds no breakpoint for an
    organism-drug pair. That value was being written straight into ``result``,
    so ``'Unknown'`` entered the stored data and every downstream rate. A
    result is now only accepted when it is one of S, I or R.

    A derived result was stored with no breakpoint edition, which the database
    now refuses and which would in any case not be reproducible. Each derived
    result carries the platform table's own version label.

    ``result_source`` records how each value arrived, so a measured result and a
    rule-derived one are never mistaken for each other later.
    """
    if ast_df.empty:
        return ast_df

    out = ast_df.copy()
    for column, default in (("auto_interpreted", False),
                            ("interpreted_result", None),
                            ("interpretation_guideline", None),
                            ("interpretation_confidence", None),
                            ("suspected_mechanism", None),
                            ("interpretation_notes", None),
                            ("result_source", None)):
        if column not in out.columns:
            out[column] = default

    for index, row in out.iterrows():
        existing = row.get("result")
        if not is_blank(existing) and str(existing).strip() in RESULT_VALUES:
            out.at[index, "result_source"] = "Imported"
            continue

        method = str(row.get("method") or "").upper()
        mic = row.get("mic_value")
        zone = row.get("zone_diameter")
        if method == "MIC" and is_blank(mic):
            continue
        if method == "DD" and is_blank(zone):
            continue
        if method not in ("MIC", "DD"):
            continue

        standard = str(row.get("guideline") or "CLSI").strip().upper() or "CLSI"

        try:
            interpretation = interpret_ast_result(
                organism=row.get("organism"),
                antibiotic=row.get("antibiotic"),
                method=method,
                mic_value=None if is_blank(mic) else float(mic),
                zone_diameter=None if is_blank(zone) else float(zone),
                guideline=standard,
            )
        except Exception as exc:                      # noqa: BLE001
            out.at[index, "interpretation_notes"] = f"Interpretation failed: {exc}"
            continue

        called = str(interpretation.get("interpretation") or "").strip()
        out.at[index, "interpretation_confidence"] = interpretation.get("confidence")
        out.at[index, "suspected_mechanism"] = interpretation.get("suspected_mechanism")
        out.at[index, "interpretation_notes"] = interpretation.get("notes")

        if called not in RESULT_VALUES:
            # No breakpoint for this pair. Leaving result empty is correct:
            # an untestable combination is not a susceptible one.
            continue

        label = platform_breakpoint_label(interpretation.get("guideline"))
        out.at[index, "result"] = called
        out.at[index, "interpreted_result"] = called
        out.at[index, "interpretation_guideline"] = interpretation.get("guideline")
        out.at[index, "auto_interpreted"] = True
        out.at[index, "result_source"] = "Rule-interpreted"
        if is_blank(row.get("guideline_version")):
            out.at[index, "guideline_version"] = label

    return out


# ---------------------------------------------------------------------------
# Workbook-level entry points
# ---------------------------------------------------------------------------

@dataclass
class UploadValidation:
    """Everything the upload path needs from validation, in one object."""

    ok: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    samples: pd.DataFrame = field(default_factory=pd.DataFrame)
    isolates: pd.DataFrame = field(default_factory=pd.DataFrame)
    ast: pd.DataFrame = field(default_factory=pd.DataFrame)
    genomics: pd.DataFrame = field(default_factory=pd.DataFrame)
    isolates_derived: bool = False
    sheets_present: Tuple[str, ...] = ()

    @property
    def errors(self) -> List[str]:
        return [i.render() for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> List[str]:
        return [i.render() for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def summary(self) -> Dict[str, int]:
        return {
            "specimens": len(self.samples),
            "isolates": len(self.isolates),
            "susceptibility_results": len(self.ast),
            "genomic_results": len(self.genomics),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }


def validate_excel_structure(file_obj) -> Tuple[bool, str, Dict]:
    """Check the workbook has the sheets the platform needs."""
    try:
        file_obj.seek(0)
        wb = load_workbook(file_obj, read_only=True)
        sheets = list(wb.sheetnames)
        wb.close()
    except Exception as exc:                          # noqa: BLE001
        return False, f"Could not read the workbook: {exc}", {}

    missing = [name for name in MANDATORY_SHEETS if name not in sheets]
    if missing:
        return False, ("The workbook must contain the sheet(s): "
                       + ", ".join(missing)), {"sheets": sheets}
    return True, "Structure valid", {"sheets": sheets}


def validate_workbook(file_obj) -> UploadValidation:
    """Validate an uploaded workbook against the contract."""
    log = _IssueLog()

    ok_structure, message, info = validate_excel_structure(file_obj)
    if not ok_structure:
        log.add("workbook", message, rule="structure")
        return UploadValidation(ok=False, issues=log.finish())

    sheet_names: List[str] = list(info.get("sheets", []))
    raw: Dict[str, pd.DataFrame] = {}
    for sheet in SHEETS:
        if sheet.name not in sheet_names:
            continue
        try:
            file_obj.seek(0)
            raw[sheet.name] = pd.read_excel(file_obj, sheet_name=sheet.name)
        except Exception as exc:                      # noqa: BLE001
            log.add(sheet.name, f"Could not read the sheet: {exc}",
                    rule="read-failure")

    return _validate_raw_frames(raw, log)


def validate_frames(samples_df: pd.DataFrame, ast_df: pd.DataFrame,
                    isolates_df: Optional[pd.DataFrame] = None,
                    genomics_df: Optional[pd.DataFrame] = None
                    ) -> UploadValidation:
    """Validate frames that did not come from a workbook.

    The KoboToolbox sync and any instrument export build their frames in memory.
    Routing them through the same function as a workbook is what stops a second,
    laxer validation path appearing beside this one -- which is how the mobile
    import came to bypass the traceability tables altogether.
    """
    raw: Dict[str, pd.DataFrame] = {
        SAMPLES_SHEET.name: samples_df if samples_df is not None else pd.DataFrame(),
        AST_SHEET.name: ast_df if ast_df is not None else pd.DataFrame(),
    }
    if isolates_df is not None and not isolates_df.empty:
        raw[ISOLATES_SHEET.name] = isolates_df
    if genomics_df is not None and not genomics_df.empty:
        raw[GENOMICS_SHEET.name] = genomics_df
    return _validate_raw_frames(raw, _IssueLog())


def _validate_raw_frames(raw: Dict[str, pd.DataFrame],
                         log: _IssueLog) -> UploadValidation:
    """The validation pipeline, on frames already read.

    Order matters. Specimens are validated first because isolates reference
    them; isolates next because susceptibility and genomic rows reference
    isolates. A reference into a sheet that failed its own validation is
    reported as an unresolved reference rather than followed.
    """
    if SAMPLES_SHEET.name not in raw or AST_SHEET.name not in raw:
        log.add("workbook",
                "Both a specimen sheet and a susceptibility sheet are needed.",
                rule="structure")
        return UploadValidation(ok=False, issues=log.finish(),
                                sheets_present=tuple(raw))

    frames: Dict[str, pd.DataFrame] = {}
    absent_headers: Dict[str, Set[str]] = {}
    for name, df in raw.items():
        sheet = next(s for s in SHEETS if s.name == name)
        usable, absent = _check_headers(df, sheet, log)
        if not usable:
            return UploadValidation(ok=False, issues=log.finish(),
                                    sheets_present=tuple(raw))
        absent_headers[name] = absent
        frames[name] = _normalise_frame(df, sheet, log)

    if frames[SAMPLES_SHEET.name].empty:
        log.add(SAMPLES_SHEET.name, "The sheet has no data rows.",
                rule="empty-sheet")
    if frames[AST_SHEET.name].empty:
        log.add(AST_SHEET.name, "The sheet has no data rows.",
                rule="empty-sheet")

    # Which sectors the file actually contains decides which sector-specific
    # columns it has to carry.
    sectors_present = {
        str(v).strip().upper()
        for v in frames[SAMPLES_SHEET.name].get("source_category", pd.Series(dtype=object))
        if not is_blank(v)
    }
    reported_missing = _check_conditional_headers(
        SAMPLES_SHEET, absent_headers.get(SAMPLES_SHEET.name, set()),
        sectors_present, log)

    samples = _validate_samples(frames[SAMPLES_SHEET.name], log,
                                already_reported=reported_missing)
    sample_ids = set(samples["sample_id"].dropna().astype(str)) if not samples.empty else set()

    isolates_supplied = ISOLATES_SHEET.name in frames and not frames[ISOLATES_SHEET.name].empty
    isolates = pd.DataFrame()
    declared_isolate_ids: Optional[Set[str]] = None
    isolate_organism: Dict[str, str] = {}
    if isolates_supplied:
        isolates = _validate_isolates(frames[ISOLATES_SHEET.name], sample_ids, log)
        # A duplicated isolate_id has already been reported as an error. Using
        # it as a lookup key would make the organism cross-check compare every
        # AST row against whichever duplicate happened to be read last, which
        # is a misleading message about a file that is already rejected.
        ids = isolates["isolate_id"].dropna().astype(str)
        declared_isolate_ids = set(ids)
        unique_ids = set(ids[~ids.duplicated(keep=False)])
        isolate_organism = {
            str(r["isolate_id"]): str(r["organism"] or "")
            for _, r in isolates.iterrows()
            if r.get("isolate_id") and str(r["isolate_id"]) in unique_ids
        }

    ast_absent = absent_headers.get(AST_SHEET.name, set())
    ast_reported: Set[str] = set()
    if "guideline_version" in ast_absent and frames[AST_SHEET.name].get("result") is not None:
        if frames[AST_SHEET.name]["result"].notna().any():
            log.add(AST_SHEET.name,
                    "The column 'guideline_version' is missing, and the sheet "
                    "carries interpreted results. Add the column and record the "
                    "edition of CLSI or EUCAST each result was read against, "
                    "for example M100-Ed34 or v14.0. Breakpoints move between "
                    "editions, so a stored S/I/R with no edition behind it "
                    "cannot be reproduced or audited later.",
                    column="guideline_version",
                    rule="missing-guideline-version")
            ast_reported.add("guideline_version")

    ast = _validate_ast(frames[AST_SHEET.name], sample_ids,
                        declared_isolate_ids, isolate_organism, log,
                        already_reported=ast_reported)

    derived = False
    if not isolates_supplied:
        # Only derive from rows that carry both a specimen and an organism;
        # rows missing either have already been reported as errors.
        usable = ast.dropna(subset=["sample_id", "organism"]) if not ast.empty else ast
        isolates, rewritten = derive_isolates(usable)
        if not ast.empty:
            ast.loc[rewritten.index, "isolate_id"] = rewritten["isolate_id"]
        derived = True

    isolate_ids = set(isolates["isolate_id"].dropna().astype(str)) if not isolates.empty else set()

    genomics = pd.DataFrame()
    if GENOMICS_SHEET.name in frames and not frames[GENOMICS_SHEET.name].empty:
        genomics = _validate_genomics(frames[GENOMICS_SHEET.name], isolate_ids, log)

    # An isolate that was declared but never tested is not an error, but it is
    # worth saying: the workbook records a culture with no susceptibility data.
    if isolates_supplied and not isolates.empty and not ast.empty:
        tested = set(ast["isolate_id"].dropna().astype(str))
        untested = sorted(isolate_ids - tested)
        for isolate_id in untested[:MAX_ISSUES_PER_RULE]:
            log.add(ISOLATES_SHEET.name,
                    f"isolate {isolate_id} has no susceptibility results in "
                    "this upload.", severity=SEVERITY_WARNING,
                    rule="isolate-untested")
        if len(untested) > MAX_ISSUES_PER_RULE:
            log.add(ISOLATES_SHEET.name,
                    f"{len(untested) - MAX_ISSUES_PER_RULE} further isolates "
                    "have no susceptibility results.",
                    severity=SEVERITY_WARNING, rule="isolate-untested-more")

    # A specimen row with no isolate is a legitimate negative culture, and a
    # surveillance system needs those to compute a positivity rate at all.
    if not samples.empty and not isolates.empty:
        with_isolates = set(isolates["sample_id"].dropna().astype(str))
        negatives = len(sample_ids - with_isolates)
        if negatives:
            log.add(SAMPLES_SHEET.name,
                    f"{negatives} specimen(s) have no isolate recorded. They "
                    "are stored as culture-negative, which is what makes a "
                    "positivity rate computable. If an organism was in fact "
                    "recovered, add it to the isolates sheet.",
                    severity=SEVERITY_WARNING, rule="specimen-no-isolate")

    issues = log.finish()
    has_errors = any(i.severity == SEVERITY_ERROR for i in issues)

    if not has_errors and not ast.empty:
        ast = perform_automated_interpretation(ast)
        # A derived result still needs an edition; interpretation supplies the
        # platform table's label, so re-check rather than assume.
        missing_version = ast[
            ast["result"].notna() & ast["guideline_version"].isna()
        ] if "guideline_version" in ast.columns else ast.iloc[0:0]
        for index in missing_version.index[:MAX_ISSUES_PER_RULE]:
            log.add(AST_SHEET.name,
                    "result is present but no breakpoint edition could be "
                    "established for it.", row=_excel_row(index),
                    column="guideline_version", rule="result-without-version")
        if len(missing_version):
            issues = log.finish()
            has_errors = any(i.severity == SEVERITY_ERROR for i in issues)

    return UploadValidation(
        ok=not has_errors,
        issues=issues,
        samples=samples,
        isolates=isolates,
        ast=ast,
        genomics=genomics,
        isolates_derived=derived,
        sheets_present=tuple(raw),
    )


def validate_upload(file_obj) -> Tuple[bool, List[str], pd.DataFrame, pd.DataFrame]:
    """Backward-compatible entry point.

    Returns the tuple the upload page has always expected. Warnings are
    appended after the errors so nothing the validator found is lost, and the
    caller can tell them apart by the ``ok`` flag.
    """
    outcome = validate_workbook(file_obj)
    messages = outcome.errors + outcome.warnings
    return outcome.ok, messages, outcome.samples, outcome.ast


def validate_samples(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Validate a specimen frame on its own. Kept for the data-quality page."""
    log = _IssueLog()
    if not _check_headers(df, SAMPLES_SHEET, log):
        issues = log.finish()
        return False, [i.render() for i in issues]
    _validate_samples(_normalise_frame(df, SAMPLES_SHEET, log), log)
    issues = log.finish()
    errors = [i.render() for i in issues if i.severity == SEVERITY_ERROR]
    return not errors, [i.render() for i in issues]


def validate_ast_results(df: pd.DataFrame,
                         sample_ids: Iterable[str]) -> Tuple[bool, List[str]]:
    """Validate an AST frame against a set of known specimen identifiers."""
    log = _IssueLog()
    if not _check_headers(df, AST_SHEET, log):
        issues = log.finish()
        return False, [i.render() for i in issues]
    _validate_ast(_normalise_frame(df, AST_SHEET, log),
                  {str(s) for s in sample_ids}, None, {}, log)
    issues = log.finish()
    errors = [i.render() for i in issues if i.severity == SEVERITY_ERROR]
    return not errors, [i.render() for i in issues]


def load_excel_sheets(file_obj) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load the two core sheets. Retained for callers that want the raw frames."""
    try:
        file_obj.seek(0)
        samples_df = pd.read_excel(file_obj, sheet_name=SAMPLES_SHEET.name)
        file_obj.seek(0)
        ast_df = pd.read_excel(file_obj, sheet_name=AST_SHEET.name)
        return samples_df, ast_df, ""
    except Exception as exc:                          # noqa: BLE001
        return pd.DataFrame(), pd.DataFrame(), f"Error loading sheets: {exc}"


__all__ = [
    "ValidationIssue", "UploadValidation",
    "validate_workbook", "validate_frames", "validate_upload",
    "validate_excel_structure",
    "validate_samples", "validate_ast_results", "load_excel_sheets",
    "perform_automated_interpretation", "derive_isolates",
    "REQUIRED_SAMPLES_COLUMNS", "REQUIRED_AST_COLUMNS",
    "VALID_SOURCE_CATEGORIES", "VALID_RESULTS", "VALID_METHODS",
    "VALID_GUIDELINES",
]
