"""Step 4 – the PBIP/TMDL project is consistent, complete and in sync with its generator."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from cockpit.config import MODEL_DIR
from cockpit.powerbi_model import MEASURES, RELATIONSHIPS, TABLES, render_files

REQUIRED_MEASURES = {
    "Actual", "Budget", "Forecast", "Variance (Abs)", "Variance %", "Actual YTD", "Budget YTD",
    "Actual PY", "YoY %", "Revenue", "Gross Margin %", "Operating Margin (EBIT) %",
    "Forecast Accuracy %", "Budget Consumption %", "Report Title",
}


def test_committed_files_match_generator() -> None:
    """Fails if someone edited TMDL by hand or forgot to run `make powerbi`."""
    for path, content in render_files().items():
        assert path.exists(), f"missing {path}"
        assert path.read_text(encoding="utf-8") == content, f"out of date: {path}"


def test_required_measures_present_with_metadata() -> None:
    names = {m.name for m in MEASURES}
    assert names >= REQUIRED_MEASURES
    for m in MEASURES:
        assert m.description, m.name
        assert m.format_string or m.name in {"Report Title", "Variance Colour", "DQ Status Colour",
                                             "Variance Commentary"}, m.name


def test_dax_references_resolve() -> None:
    measures = {m.name for m in MEASURES}
    columns = {(t.name, c.name) for t in TABLES for c in t.columns}
    tables = {t.name for t in TABLES}
    for m in MEASURES:
        for table, column in re.findall(r"'([^']+)'\[([^\]]+)\]", m.expression):
            assert (table, column) in columns, f"{m.name}: '{table}'[{column}]"
        for ref in re.findall(r"(?<!')\[([^\]]+)\]", m.expression):
            assert ref in measures, f"{m.name}: unknown measure [{ref}]"
        for table in re.findall(r"(?:REMOVEFILTERS|COUNTROWS)\s*\(\s*'([^']+)'", m.expression):
            assert table in tables, f"{m.name}: unknown table {table}"


def test_relationships_are_star_shaped() -> None:
    columns = {(t.name, c.name) for t in TABLES for c in t.columns}
    for r in RELATIONSHIPS:
        assert (r.from_table, r.from_column) in columns
        assert (r.to_table, r.to_column) in columns


def test_date_table_marked() -> None:
    date = next(t for t in TABLES if t.name == "Date")
    assert date.is_date_table
    assert any(c.is_key and c.data_type == "dateTime" for c in date.columns)


@pytest.mark.parametrize("table", TABLES, ids=lambda t: t.name)
def test_power_query_columns_match_exported_csv(table) -> None:  # noqa: ANN001
    csv = MODEL_DIR / table.file
    if not csv.exists():
        pytest.skip("run `make build` first")
    header = list(pd.read_csv(csv, nrows=0).columns)
    assert header == [c.source for c in table.columns]


def test_tmdl_uses_tabs_only() -> None:
    for path, content in render_files().items():
        if path.suffix == ".tmdl":
            for n, line in enumerate(content.splitlines(), 1):
                assert not re.match(r"^ +\S", line), f"{path.name}:{n} indented with spaces"


def test_json_files_are_valid() -> None:
    for path, content in render_files().items():
        if path.suffix in {".json", ".pbir", ".pbism", ".pbip"}:
            doc = json.loads(content)
            assert doc["$schema"].startswith("https://developer.microsoft.com/json-schemas/")


def test_measures_dax_contains_every_measure() -> None:
    dax = (Path(__file__).parents[1] / "powerbi" / "measures.dax").read_text(encoding="utf-8")
    for m in MEASURES:
        assert f"'_Measures'[{m.name}] =" in dax
