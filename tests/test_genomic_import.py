"""Attaching sequencing results to isolates already stored.

Sequencing happens weeks or months after culture, so results arrive on their
own and must find isolates that are already in the database. The combined
workbook upload could not do that: it matched a genomics row only against
isolates in the *same* file and skipped the rest without a word, so a laboratory
uploading results for isolates it had submitted months earlier got no rows and
no error.

These tests cover the matching contract rather than the database write, so they
run without a connection.
"""

import pandas as pd
import pytest

from src import ingest


class _FakeCursor:
    """Stands in for the isolate lookup."""

    def __init__(self, rows):
        self._rows = rows
        self._result = []

    def execute(self, sql, params=None):
        wanted = params[-1] if params else []
        if params and len(params) == 2:          # dataset-scoped lookup
            dataset, ids = params
            self._result = [r for r in self._rows
                            if r["isolate_id"] in ids
                            and r["dataset_id"] == dataset]
        else:
            self._result = [r for r in self._rows if r["isolate_id"] in wanted]

    def fetchall(self):
        return self._result


def test_an_isolate_in_one_dataset_resolves():
    cur = _FakeCursor([{"isolate_id": "ISO-1", "dataset_id": "d1"}])
    resolved, ambiguous = ingest._resolve_isolates(cur, ["ISO-1"], None)
    assert resolved == {"ISO-1": "d1"}
    assert ambiguous == []


def test_an_isolate_in_two_datasets_is_refused_not_guessed():
    """Attaching a genome to the wrong isolate is worse than not attaching it,
    because nothing downstream would reveal the error."""
    cur = _FakeCursor([{"isolate_id": "ISO-1", "dataset_id": "d1"},
                       {"isolate_id": "ISO-1", "dataset_id": "d2"}])
    resolved, ambiguous = ingest._resolve_isolates(cur, ["ISO-1"], None)
    assert resolved == {}
    assert ambiguous == ["ISO-1"]


def test_naming_the_dataset_removes_the_ambiguity():
    cur = _FakeCursor([{"isolate_id": "ISO-1", "dataset_id": "d1"},
                       {"isolate_id": "ISO-1", "dataset_id": "d2"}])
    resolved, ambiguous = ingest._resolve_isolates(cur, ["ISO-1"], "d2")
    assert resolved == {"ISO-1": "d2"}
    assert ambiguous == []


def test_an_unknown_isolate_resolves_to_nothing():
    cur = _FakeCursor([{"isolate_id": "ISO-1", "dataset_id": "d1"}])
    resolved, ambiguous = ingest._resolve_isolates(cur, ["ISO-9"], None)
    assert resolved == {} and ambiguous == []


def test_blank_and_duplicate_ids_are_tolerated():
    cur = _FakeCursor([{"isolate_id": "ISO-1", "dataset_id": "d1"}])
    resolved, _ = ingest._resolve_isolates(cur, ["ISO-1", "ISO-1", "", None],
                                           None)
    assert resolved == {"ISO-1": "d1"}


def test_an_empty_frame_is_refused_with_a_reason():
    result = ingest.import_genomic_results(pd.DataFrame())
    assert not result.ok
    assert "no genomic rows" in result.message.lower()


def test_a_frame_without_isolate_id_is_refused_with_a_reason():
    frame = pd.DataFrame([{"genomic_id": "SEQ-1", "amr_genes": "mecA"}])
    result = ingest.import_genomic_results(frame)
    assert not result.ok
    assert "isolate_id" in result.message


def test_the_result_reports_what_it_could_not_place():
    """An import that quietly stores a fraction of what it was given is worse
    than one that fails: the gap looks like an absence of sequencing."""
    result = ingest.GenomicImport(True, "ok", stored=3,
                                  unmatched=["A", "B"], ambiguous=["C"])
    assert result.unmatched == ["A", "B"]
    assert result.ambiguous == ["C"]
