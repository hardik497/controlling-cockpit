"""Step 3 – the Excel workbook has real formulas (XLOOKUP / SUMIFS), not pasted values."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook

from cockpit.excel_workbook import build_workbook


@pytest.fixture(scope="module")
def workbook(db_path: Path, raw_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Workbook:
    out = tmp_path_factory.mktemp("xl") / "recon.xlsx"
    build_workbook(output=out, db_path=db_path, raw_dir=raw_dir)
    return load_workbook(out)


def test_sheets_present(workbook: Workbook) -> None:
    assert workbook.sheetnames == ["README", "Summary", "Reconciliation", "Actuals",
                                   "Ledger_Totals", "Quarantine", "Data"]


def test_reconciliation_uses_xlookup(workbook: Workbook) -> None:
    ws = workbook["Reconciliation"]
    formulas = [c.value for row in ws.iter_rows(min_row=5, max_row=10) for c in row
                if isinstance(c.value, str) and c.value.startswith("=")]
    assert sum("_xlfn.XLOOKUP(" in f for f in formulas) >= 20
    assert ws.conditional_formatting, "conditional formatting missing"


def test_reconciliation_ties_out_on_values(workbook: Workbook) -> None:
    """Ledger = Warehouse + Quarantine per account (checks the data behind the formulas)."""
    led = {r[0]: r[2] for r in workbook["Ledger_Totals"].iter_rows(min_row=5, values_only=True)}
    qua = {r[0]: r[2] for r in workbook["Quarantine"].iter_rows(min_row=5, values_only=True)}
    act_ws = workbook["Actuals"]
    wh = {}
    for row in act_ws.iter_rows(min_row=5, values_only=True):
        wh[row[0]] = sum(v for v in row[3:-1] if isinstance(v, (int, float)))
    for account, ledger_total in led.items():
        diff = ledger_total - wh.get(account, 0) - qua.get(account, 0)
        assert abs(diff) < 0.05, account


def test_summary_is_formula_based(workbook: Workbook) -> None:
    ws = workbook["Summary"]
    values = [ws[f"C{r}"].value for r in range(8, 12)]
    assert all(isinstance(v, str) and v.startswith("=SUMIFS(") for v in values)


def test_data_sheet_is_excel_table(workbook: Workbook) -> None:
    assert "tblFinance" in workbook["Data"].tables
