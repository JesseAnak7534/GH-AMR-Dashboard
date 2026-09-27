"""
Builds the blank upload workbook from the column contract in ``upload_schema``.

The previous template builder kept its own hard-coded column list and wrote the
file to the relative path ``templates/AMR_ENV_FOOD_template_v1.xlsx`` before
reading it back as bytes. That failed on a read-only filesystem, depended on the
working directory, and let the template drift away from what the validator
accepted. This builder reads the contract, writes to a ``BytesIO``, and touches
no disk.

Every controlled-vocabulary column gets an Excel dropdown, so most of the
validation the platform performs is visible to the person filling the sheet
rather than reported back after an upload fails.
"""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Sequence, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src.upload_schema import (
    GENOMICS_SHEET,
    SHEETS,
    TEMPLATE_VERSION,
    Column,
    Sheet,
)

# Excel refuses an inline dropdown list longer than 255 characters including the
# quoting, and splits on commas, so a vocabulary containing either goes to a
# hidden lookup sheet instead.
_INLINE_LIST_LIMIT = 240
_LOOKUP_SHEET = "_lists"

_HEADER_FILL_REQUIRED = PatternFill("solid", fgColor="0E7490")
_HEADER_FILL_CONDITIONAL = PatternFill("solid", fgColor="0369A1")
_HEADER_FILL_OPTIONAL = PatternFill("solid", fgColor="475569")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
_TITLE_FONT = Font(bold=True, size=13)
_SECTION_FONT = Font(bold=True, size=11)


# ---------------------------------------------------------------------------
# Example rows
#
# Deliberately spans sectors: a human blood culture with a full care episode, a
# food isolate, and an environmental grab. Someone reading the template can see
# from the examples that patient columns are left empty for non-human rows.
# ---------------------------------------------------------------------------

_EXAMPLE_SAMPLES: Tuple[Dict[str, object], ...] = (
    {
        "sample_id": "GH-2601-0001",
        "lab_name": "",  # filled from the approved list at build time
        "collection_date": "2026-01-14",
        "collection_time": "08:30",
        "source_category": "HUMAN",
        "source_type": "clinical_specimen",
        "site_type": "Teaching hospital",
        "region": "Greater Accra",
        "district": "Accra Metropolitan",
        "latitude": 5.6037,
        "longitude": -0.1870,
        "accession_number": "LAB/26/00412",
        "specimen_type": "Blood",
        "specimen_detail": "Peripheral blood culture, set 1",
        "collected_by": "Ward nurse",
        "receipt_date": "2026-01-14",
        "receipt_time": "10:05",
        "condition_on_receipt": "Acceptable",
        "sampling_purpose": "Routine diagnostic",
        "facility_code": "KBTH",
        "facility_name": "Korle Bu Teaching Hospital",
        "local_patient_id": "MRN-884213",
        "sex": "F",
        "age_years": 4,
        "patient_type": "Inpatient",
        "ward": "Paediatric Ward B",
        "ward_type": "Paediatric",
        "ward_at_collection": "Paediatric ICU",
        "ward_type_at_collection": "ICU",
        "admission_date": "2026-01-09",
        "admission_source": "Referral from district hospital",
    },
    {
        "sample_id": "GH-2601-0002",
        "lab_name": "",
        "collection_date": "2026-01-16",
        "source_category": "FOOD",
        "source_type": "raw_chicken",
        "site_type": "Retail market",
        "region": "Ashanti",
        "district": "Kumasi Metropolitan",
        "latitude": 6.6885,
        "longitude": -1.6244,
        "specimen_type": "Other",
        "specimen_detail": "Chicken carcass rinse",
        "receipt_date": "2026-01-16",
        "condition_on_receipt": "Acceptable",
        "sampling_purpose": "Surveillance",
        "food_commodity": "Poultry",
        "food_matrix": "chicken",
        "food_stage": "Retail",
    },
    {
        "sample_id": "GH-2601-0003",
        "lab_name": "",
        "collection_date": "2026-01-18",
        "source_category": "ENVIRONMENT",
        "source_type": "treated_water",
        "site_type": "Wastewater treatment plant",
        "region": "Greater Accra",
        "district": "Ga West",
        "latitude": 5.6500,
        "longitude": -0.2600,
        "specimen_type": "Other",
        "specimen_detail": "Grab sample, 1 L",
        "receipt_date": "2026-01-18",
        "condition_on_receipt": "Acceptable",
        "sampling_purpose": "Surveillance",
        "water_body": "Densu",
        "catchment": "Densu basin",
        "treatment_stage": "Effluent",
        "environment_matrix": "treated_water",
        "sampling_point": "Outfall channel, 20 m downstream",
    },
)

_EXAMPLE_ISOLATES: Tuple[Dict[str, object], ...] = (
    {
        "sample_id": "GH-2601-0001",
        "isolate_id": "GH-2601-0001-1",
        "isolate_number": 1,
        "organism": "Klebsiella pneumoniae",
        "organism_code": "kpn",
        "identification_method": "MALDI-TOF",
        "identification_date": "2026-01-16",
        "is_significant": "Yes",
        "notes": "Pure growth from both bottles",
    },
    {
        "sample_id": "GH-2601-0002",
        "isolate_id": "GH-2601-0002-1",
        "isolate_number": 1,
        "organism": "Salmonella enterica",
        "organism_code": "sal",
        "identification_method": "Automated biochemical",
        "identification_date": "2026-01-19",
        "is_significant": "Yes",
    },
    {
        "sample_id": "GH-2601-0003",
        "isolate_id": "GH-2601-0003-1",
        "isolate_number": 1,
        "organism": "Escherichia coli",
        "organism_code": "eco",
        "identification_method": "Chromogenic agar",
        "identification_date": "2026-01-21",
    },
)

_EXAMPLE_AST: Tuple[Dict[str, object], ...] = (
    {
        "sample_id": "GH-2601-0001", "isolate_id": "GH-2601-0001-1",
        "organism": "Klebsiella pneumoniae", "antibiotic": "Ceftriaxone",
        "method": "MIC", "ast_instrument": "VITEK 2", "mic_operator": ">=",
        "mic_value": 64, "result": "R", "guideline": "CLSI",
        "guideline_version": "M100-Ed34", "qc_status": "Pass",
        "qc_strain": "ATCC 700603", "test_date": "2026-01-17",
        "verified_by": "Senior biomedical scientist",
    },
    {
        "sample_id": "GH-2601-0001", "isolate_id": "GH-2601-0001-1",
        "organism": "Klebsiella pneumoniae", "antibiotic": "Meropenem",
        "method": "MIC", "ast_instrument": "VITEK 2", "mic_operator": "<=",
        "mic_value": 0.25, "result": "S", "guideline": "CLSI",
        "guideline_version": "M100-Ed34", "qc_status": "Pass",
        "test_date": "2026-01-17",
    },
    {
        "sample_id": "GH-2601-0001", "isolate_id": "GH-2601-0001-1",
        "organism": "Klebsiella pneumoniae", "antibiotic": "Ciprofloxacin",
        "method": "DD", "zone_diameter": 14, "result": "I", "guideline": "CLSI",
        "guideline_version": "M100-Ed34", "qc_status": "Pass",
        "test_date": "2026-01-17",
    },
    {
        "sample_id": "GH-2601-0002", "isolate_id": "GH-2601-0002-1",
        "organism": "Salmonella enterica", "antibiotic": "Ampicillin",
        "method": "DD", "zone_diameter": 9, "result": "R", "guideline": "CLSI",
        "guideline_version": "M100-Ed34", "test_date": "2026-01-20",
    },
    {
        "sample_id": "GH-2601-0003", "isolate_id": "GH-2601-0003-1",
        "organism": "Escherichia coli", "antibiotic": "Ciprofloxacin",
        "method": "DD", "zone_diameter": 27, "result": "S", "guideline": "EUCAST",
        "guideline_version": "v14.0", "test_date": "2026-01-22",
    },
)

_EXAMPLE_GENOMICS: Tuple[Dict[str, object], ...] = (
    {
        "genomic_id": "SEQ-2026-0117",
        "isolate_id": "GH-2601-0001-1",
        "run_id": "RUN-2026-03",
        "platform": "Illumina MiSeq",
        "run_date": "2026-02-02",
        "library_id": "BC07",
        "read_path": "s3://icbb-amrss-reads/2026/SEQ-2026-0117_R1.fastq.gz",
        "read_checksum": "sha256:9f2c1b...",
        "assembly_path": "s3://icbb-amrss-assemblies/SEQ-2026-0117.fasta",
        "assembly_checksum": "sha256:4ad8e0...",
        "total_reads": 3180000,
        "mean_depth": 78.4,
        "coverage_breadth": 99.1,
        "contamination_pct": 0.6,
        "n50": 184000,
        "contig_count": 96,
        "qc_status": "Pass",
        "assembler": "SPAdes",
        "assembler_version": "3.15.5",
        "pipeline_name": "bactopia",
        "pipeline_version": "3.0.1",
        "amr_db_name": "ResFinder",
        "amr_db_version": "2024-08-06",
        "species_confirmed": "Klebsiella pneumoniae",
        "mlst_scheme": "kpneumoniae",
        "sequence_type": "ST147",
        "amr_genes": "blaCTX-M-15;blaOXA-1;qnrB1",
        "amr_mutations": "gyrA_S83I;parC_S80I",
        "plasmid_replicons": "IncFIB;IncFII",
        "cluster_method": "cgMLST",
        "cluster_id": "CL-2026-004",
        "analysis_date": "2026-02-10",
        "analysed_by": "Bioinformatics unit",
        "review_status": "Accepted",
        "reviewed_by": "Laboratory head",
    },
)

_EXAMPLES: Dict[str, Tuple[Dict[str, object], ...]] = {
    "samples": _EXAMPLE_SAMPLES,
    "isolates": _EXAMPLE_ISOLATES,
    "ast_results": _EXAMPLE_AST,
    "genomics": _EXAMPLE_GENOMICS,
}


# ---------------------------------------------------------------------------
# Dropdowns
# ---------------------------------------------------------------------------

def _set_text(cell, value: str) -> None:
    """Store a value as text, whatever it looks like.

    openpyxl infers a formula from any string beginning with ``=``, so the MIC
    operator vocabulary (``=``, ``<=``, ``>=``) would otherwise be written as
    broken formulas. Assigning the value and then pinning the type keeps it
    text.
    """
    cell.value = value
    cell.data_type = "s"


def _inline_list_usable(values: Sequence[str]) -> bool:
    """Whether a vocabulary can be an inline Excel list.

    Excel splits an inline list on commas and caps the whole formula, so a
    vocabulary containing a comma or one that is simply long has to live in a
    lookup range instead.
    """
    if any("," in str(v) or '"' in str(v) for v in values):
        return False
    return len(",".join(str(v) for v in values)) <= _INLINE_LIST_LIMIT


def _write_lookup_column(lookup_ws, col_index: int, title: str,
                         values: Sequence[str]) -> str:
    """Write a vocabulary down one column of the lookup sheet.

    Returns the absolute range reference for a dropdown to point at. Values are
    forced to text: a bare ``=`` or ``>=`` written as a cell value would
    otherwise be stored as a formula.
    """
    letter = get_column_letter(col_index)
    lookup_ws[f"{letter}1"] = title
    for offset, value in enumerate(values, start=2):
        cell = lookup_ws[f"{letter}{offset}"]
        _set_text(cell, str(value))
    return f"'{_LOOKUP_SHEET}'!${letter}$2:${letter}${len(values) + 1}"


def _add_dropdown(ws, column_letter: str, values: Sequence[str],
                  lookup_ws, lookup_state: Dict[str, object],
                  title: str, last_row: int) -> None:
    """Attach a list validation to one column of a data sheet."""
    if not values:
        return
    if _inline_list_usable(values):
        formula = '"' + ",".join(str(v) for v in values) + '"'
    else:
        key = f"{title}:{len(values)}"
        if key not in lookup_state:
            lookup_state["_next"] = lookup_state.get("_next", 1)
            ref = _write_lookup_column(lookup_ws, lookup_state["_next"],
                                       title, values)
            lookup_state[key] = lookup_state["_next"]
            lookup_state[f"ref:{key}"] = ref
            lookup_state["_next"] += 1
        formula = lookup_state[f"ref:{key}"]

    dv = DataValidation(type="list", formula1=formula, allow_blank=True,
                        showDropDown=False)
    dv.error = "Value is not in the controlled list for this column."
    dv.errorTitle = "Not a recognised value"
    dv.prompt = "Choose from the list."
    dv.promptTitle = title
    ws.add_data_validation(dv)
    dv.add(f"{column_letter}2:{column_letter}{last_row}")


# ---------------------------------------------------------------------------
# Sheet writers
# ---------------------------------------------------------------------------

def _requiredness(col: Column) -> str:
    if col.required:
        return "Required"
    if col.is_conditional:
        return "Required for " + ", ".join(col.required_for_sectors)
    return "Optional"


def _header_fill(col: Column) -> PatternFill:
    if col.required:
        return _HEADER_FILL_REQUIRED
    if col.is_conditional:
        return _HEADER_FILL_CONDITIONAL
    return _HEADER_FILL_OPTIONAL


def _column_width(col: Column) -> int:
    return max(12, min(28, len(col.name) + 4))


def _write_data_sheet(wb: Workbook, sheet: Sheet, lab_names: Sequence[str],
                      lookup_ws, lookup_state: Dict[str, object],
                      data_rows: int = 500) -> None:
    ws = wb.create_sheet(sheet.name)
    last_row = max(data_rows, len(_EXAMPLES.get(sheet.name, ())) + 1)

    for idx, col in enumerate(sheet.columns, start=1):
        letter = get_column_letter(idx)
        cell = ws[f"{letter}1"]
        cell.value = col.name
        cell.font = _HEADER_FONT
        cell.fill = _header_fill(col)
        cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.column_dimensions[letter].width = _column_width(col)

        # The header comment carries the data dictionary to the point of entry.
        vocabulary = col.vocabulary
        if col.name == "lab_name":
            vocabulary = tuple(lab_names)
        elif col.kind == "boolean":
            vocabulary = ("Yes", "No")
        if vocabulary:
            _add_dropdown(ws, letter, vocabulary, lookup_ws, lookup_state,
                          col.name, last_row)

    ws.freeze_panes = "A2"

    for row_offset, example in enumerate(_EXAMPLES.get(sheet.name, ()), start=2):
        for idx, col in enumerate(sheet.columns, start=1):
            if col.name not in example:
                continue
            value = example[col.name]
            if col.name == "lab_name":
                value = lab_names[0] if lab_names else ""
            cell = ws.cell(row=row_offset, column=idx)
            if isinstance(value, str):
                _set_text(cell, value)
            else:
                cell.value = value


def _write_dictionary_sheet(wb: Workbook, lab_count: int) -> None:
    """A data dictionary the uploader can actually read.

    Every column, what it means, whether it is required, and the exact values
    accepted. This is the document the validator's error messages refer back to.
    """
    ws = wb.create_sheet("Data dictionary", 0)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 74
    ws.column_dimensions["E"].width = 52

    row = 1
    ws[f"A{row}"] = f"ICBB-AMRSS upload template, version {TEMPLATE_VERSION}"
    ws[f"A{row}"].font = _TITLE_FONT
    row += 2

    for paragraph in (
        "Fill one row per specimen on the samples sheet, one row per organism "
        "recovered on the isolates sheet, and one row per antibiotic tested on "
        "the ast_results sheet.",
        "A culture tested against twelve antibiotics is ONE isolate row and "
        "twelve ast_results rows, all sharing the same isolate_id. Repeating the "
        "isolate_id is correct and expected.",
        "The isolates and genomics sheets are optional. Without an isolates "
        "sheet the platform derives one isolate per specimen and organism from "
        "the ast_results sheet.",
        "local_patient_id is hashed with a facility-specific secret at upload "
        "and then discarded. The platform never stores a hospital patient "
        "number. It is collected only so that repeat specimens from one patient "
        "can be linked, which is what makes first-isolate deduplication and "
        "infection-onset classification possible.",
        "Columns shaded dark teal are required for every row. Columns shaded "
        "blue are required only for the sectors named below. Grey columns are "
        "optional but improve what the platform can report.",
    ):
        ws[f"A{row}"] = paragraph
        ws[f"A{row}"].alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        ws.row_dimensions[row].height = 30
        row += 1

    row += 1
    for heading, letter in (("Sheet", "A"), ("Column", "B"), ("Requirement", "C"),
                            ("Meaning", "D"), ("Accepted values", "E")):
        cell = ws[f"{letter}{row}"]
        cell.value = heading
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL_REQUIRED
    header_row = row
    row += 1

    for sheet in SHEETS:
        label = sheet.name + (" (optional sheet)" if sheet.optional else "")
        ws[f"A{row}"] = label
        ws[f"A{row}"].font = _SECTION_FONT
        ws[f"D{row}"] = sheet.description
        ws[f"D{row}"].alignment = Alignment(wrap_text=True, vertical="top")
        row += 1

        for col in sheet.columns:
            ws[f"A{row}"] = ""
            ws[f"B{row}"] = col.name
            ws[f"C{row}"] = _requiredness(col)
            ws[f"D{row}"] = col.description
            ws[f"D{row}"].alignment = Alignment(wrap_text=True, vertical="top")

            if col.name == "lab_name":
                accepted = f"One of the {lab_count} approved laboratories (dropdown)"
            elif col.vocabulary:
                accepted = " | ".join(col.vocabulary)
            elif col.kind == "date":
                accepted = "Date, YYYY-MM-DD"
            elif col.kind == "time":
                accepted = "Time, HH:MM (24-hour)"
            elif col.kind == "boolean":
                accepted = "Yes | No"
            elif col.kind == "list":
                accepted = "Semicolon-separated list"
            elif col.kind in ("number", "integer"):
                bounds = []
                if col.minimum is not None:
                    bounds.append(f"min {col.minimum:g}")
                if col.maximum is not None:
                    bounds.append(f"max {col.maximum:g}")
                accepted = ("Whole number" if col.kind == "integer" else "Number")
                if bounds:
                    accepted += " (" + ", ".join(bounds) + ")"
            else:
                accepted = "Free text"
            if col.sectors:
                accepted += "  [used for: " + ", ".join(col.sectors) + "]"
            ws[f"E{row}"] = accepted
            ws[f"E{row}"].alignment = Alignment(wrap_text=True, vertical="top")
            row += 1
        row += 1

    ws.freeze_panes = f"A{header_row + 1}"


def _write_extra_sheet(wb: Workbook, name: str, frame,
                       header_colour: str) -> None:
    """Append a sheet supplied by a caller, for example a One Health sheet.

    These sheets are not described by the upload contract, so they get headers
    and example rows but no dropdowns or dictionary entries. They exist so the
    platform can still offer one workbook rather than several.
    """
    ws = wb.create_sheet(name)
    fill = PatternFill("solid", fgColor=header_colour)
    columns = list(frame.columns)

    for idx, column in enumerate(columns, start=1):
        letter = get_column_letter(idx)
        cell = ws[f"{letter}1"]
        cell.value = str(column)
        cell.font = _HEADER_FONT
        cell.fill = fill
        cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.column_dimensions[letter].width = max(12, min(28, len(str(column)) + 4))

    for row_offset, (_, record) in enumerate(frame.iterrows(), start=2):
        for idx, column in enumerate(columns, start=1):
            value = record[column]
            if value is None:
                continue
            cell = ws.cell(row=row_offset, column=idx)
            if isinstance(value, str):
                _set_text(cell, value)
            else:
                try:
                    if value != value:      # NaN
                        continue
                except TypeError:
                    pass
                cell.value = value

    ws.freeze_panes = "A2"


def build_template(lab_names: Optional[Sequence[str]] = None,
                   extra_sheets: Optional[Sequence[Tuple[str, object, str]]] = None
                   ) -> bytes:
    """Return the upload workbook as bytes. Writes nothing to disk.

    ``extra_sheets`` takes ``(sheet_name, dataframe, header_colour)`` triples and
    appends them after the contract sheets. It is what lets the One Health
    workbook add its PPS, AMU and AMC sheets without maintaining a second copy
    of the samples and ast_results definitions -- the drift that let the
    downloadable template and the validator disagree.
    """
    if lab_names is None:
        try:
            from src.lab_management import get_lab_names
            lab_names = get_lab_names()
        except Exception:
            lab_names = []
    labs: List[str] = [str(name) for name in (lab_names or []) if str(name).strip()]

    wb = Workbook()
    wb.remove(wb.active)

    lookup_ws = wb.create_sheet(_LOOKUP_SHEET)
    lookup_state: Dict[str, object] = {}

    for sheet in SHEETS:
        _write_data_sheet(wb, sheet, labs, lookup_ws, lookup_state)

    for name, frame, colour in (extra_sheets or ()):
        _write_extra_sheet(wb, name, frame, colour)

    _write_dictionary_sheet(wb, len(labs))
    lookup_ws.sheet_state = "hidden"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


__all__ = ["build_template"]
