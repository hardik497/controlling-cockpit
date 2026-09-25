"""Build the Excel reconciliation workbook ``excel/controlling_reconciliation.xlsx``.

Sheets:

* ``README``          – purpose of the workbook and how to read the checks.
* ``Summary``         – formula-based (SUMIFS) budget vs. actual by department and P&L,
                        with a fiscal-year selector.
* ``Reconciliation``  – XLOOKUP formulas comparing ledger totals (raw CSV) against warehouse
                        totals (SQL) and quarantined amounts, with conditional formatting.
* ``Actuals``         – warehouse actuals by account (rows) and month (columns).
* ``Ledger_Totals``   – raw ledger totals by account, computed independently from the CSV.
* ``Quarantine``      – quarantined (rejected) amounts by account from fact_finance_rejected.
* ``Data``            – flat fact table (Excel Table ``tblFinance``) – source for SUMIFS and
                        for the manually built pivot table (see docs/excel_pivot_steps.md).

All calculations in Summary and Reconciliation are live Excel formulas – nothing is
hard-coded – so a reviewer can trace every number. Values are computed when the file is
opened in Excel (full recalculation on load is enabled).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from cockpit.config import COMPANY, EXCEL_DIR, FISCAL_YEARS, RAW_DIR, WAREHOUSE_PATH

OUTPUT_PATH: Path = EXCEL_DIR / "controlling_reconciliation.xlsx"

NAVY = "1F3864"
FILL_HEADER = PatternFill("solid", fgColor=NAVY)
FILL_INPUT = PatternFill("solid", fgColor="FFF2CC")
FILL_RED = PatternFill("solid", fgColor="F8CBAD")
FILL_AMBER = PatternFill("solid", fgColor="FFE699")
FILL_GREEN = PatternFill("solid", fgColor="C6EFCE")
FONT_HEADER = Font(bold=True, color="FFFFFF")
FONT_TITLE = Font(bold=True, size=14, color=NAVY)
FONT_BOLD = Font(bold=True)
FONT_NOTE = Font(italic=True, color="595959")
THIN_TOP = Border(top=Side(style="thin"))
FMT_EUR = '#,##0.00;[Red]-#,##0.00'
FMT_EUR0 = '#,##0;[Red]-#,##0'
FMT_PCT = '0.0%;[Red]-0.0%'


# --------------------------------------------------------------------------------------
# Data extraction
# --------------------------------------------------------------------------------------


def load_frames(db_path: Path = WAREHOUSE_PATH, raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    """Query the warehouse (and the raw ledger) for everything the workbook needs."""
    con = duckdb.connect(str(db_path), read_only=True)
    frames = {
        "actuals": con.execute(
            """
            SELECT account_code, account_name, pnl_group, period, SUM(amount) AS amount
            FROM v_finance
            WHERE scenario = 'Actual'
            GROUP BY account_code, account_name, pnl_group, period
            ORDER BY account_code, period
            """
        ).df(),
        "quarantine": con.execute(
            """
            SELECT account_code, COUNT(*) AS rows_rejected, SUM(amount) AS amount_rejected
            FROM fact_finance_rejected
            WHERE scenario = 'Actual'
            GROUP BY account_code
            ORDER BY account_code
            """
        ).df(),
        "data": con.execute(
            """
            SELECT fiscal_year, period, department, cost_centre_code, cost_centre_name,
                   pnl_category, pnl_group, account_code, account_name, scenario,
                   CAST(amount AS DOUBLE) AS amount
            FROM v_finance
            ORDER BY period, account_code, cost_centre_code, scenario
            """
        ).df(),
    }
    con.close()

    # Ledger totals are computed straight from the raw CSV with pandas – deliberately a
    # different code path than the SQL warehouse, so the reconciliation is meaningful.
    gl = pd.read_csv(raw_dir / "gl_actuals.csv", dtype={"account_code": str})
    frames["ledger"] = (
        gl.groupby("account_code", as_index=False)
        .agg(rows_booked=("entry_id", "count"), ledger_total=("amount", "sum"))
        .sort_values("account_code")
    )
    frames["ledger"]["ledger_total"] = frames["ledger"]["ledger_total"].round(2)
    return frames


# --------------------------------------------------------------------------------------
# Sheet helpers
# --------------------------------------------------------------------------------------


def _header(ws: Worksheet, row: int, values: list[str], start_col: int = 1) -> None:
    for offset, value in enumerate(values):
        cell = ws.cell(row=row, column=start_col + offset, value=value)
        cell.fill = FILL_HEADER
        cell.font = FONT_HEADER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _widths(ws: Worksheet, widths: dict[str, float]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def _title(ws: Worksheet, title: str, subtitle: str) -> None:
    ws["A1"] = title
    ws["A1"].font = FONT_TITLE
    ws["A2"] = subtitle
    ws["A2"].font = FONT_NOTE


# --------------------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------------------


def write_actuals(ws: Worksheet, actuals: pd.DataFrame) -> tuple[int, int, str]:
    """Write actuals by account x month. Returns (first_row, last_row, total_col_letter)."""
    _title(ws, "Actuals by account and month (EUR)",
           "Source: DuckDB warehouse, fact_finance, scenario = Actual (after DQ quarantine)")
    wide = actuals.pivot_table(index=["account_code", "account_name", "pnl_group"],
                               columns="period", values="amount", aggfunc="sum",
                               fill_value=0).reset_index()
    periods = [c for c in wide.columns if c not in ("account_code", "account_name", "pnl_group")]
    header_row = 4
    _header(ws, header_row, ["Account", "Account name", "P&L group", *periods, "Total"])
    total_col = get_column_letter(4 + len(periods))
    first_period_col, last_period_col = "D", get_column_letter(3 + len(periods))
    for i, rec in enumerate(wide.itertuples(index=False), start=header_row + 1):
        ws.cell(row=i, column=1, value=rec[0])
        ws.cell(row=i, column=2, value=rec[1])
        ws.cell(row=i, column=3, value=rec[2])
        for j, value in enumerate(rec[3:], start=4):
            ws.cell(row=i, column=j, value=round(float(value), 2)).number_format = FMT_EUR0
        total = ws[f"{total_col}{i}"]
        total.value = f"=SUM({first_period_col}{i}:{last_period_col}{i})"
        total.number_format = FMT_EUR
        total.font = FONT_BOLD
    last_row = header_row + len(wide)
    ws.freeze_panes = "D5"
    _widths(ws, {"A": 10, "B": 26, "C": 20, total_col: 16})
    for j in range(4, 4 + len(periods)):
        ws.column_dimensions[get_column_letter(j)].width = 12
    return header_row + 1, last_row, total_col


def write_simple_table(ws: Worksheet, title: str, subtitle: str, frame: pd.DataFrame,
                       headers: list[str], money_cols: set[int]) -> int:
    """Write a small table starting in row 4 and return the last data row."""
    _title(ws, title, subtitle)
    _header(ws, 4, headers)
    for i, rec in enumerate(frame.itertuples(index=False), start=5):
        for j, value in enumerate(rec, start=1):
            val = round(float(value), 2) if j in money_cols else value
            if hasattr(val, "item"):
                val = val.item()  # numpy scalar -> python
            cell = ws.cell(row=i, column=j, value=val)
            if j in money_cols:
                cell.number_format = FMT_EUR
    _widths(ws, {"A": 12, "B": 14, "C": 18})
    ws.freeze_panes = "A5"
    return 4 + len(frame)


def write_reconciliation(ws: Worksheet, accounts: list[str], act: tuple[int, int, str],
                         ledger_last: int, quarantine_last: int) -> None:
    """Write the XLOOKUP-based reconciliation sheet."""
    act_first, act_last, act_total_col = act
    _title(ws, "Reconciliation: ledger (raw CSV) vs. warehouse (SQL)",
           "Ledger total - Warehouse total must be fully explained by quarantined rows. "
           "Unexplained difference must be 0.")
    headers = ["Account", "Account name", "Ledger rows", "Ledger total (raw)",
               "Warehouse total (SQL)", "Difference", "Quarantined (DQ)",
               "Unexplained difference", "Status"]
    _header(ws, 4, headers)
    ws.row_dimensions[4].height = 32

    act_a = f"Actuals!$A${act_first}:$A${act_last}"
    act_b = f"Actuals!$B${act_first}:$B${act_last}"
    act_tot = f"Actuals!${act_total_col}${act_first}:${act_total_col}${act_last}"
    led_a, led_b, led_c = (f"Ledger_Totals!${c}$5:${c}${ledger_last}" for c in "ABC")
    q_a, q_c = (f"Quarantine!${c}$5:${c}${quarantine_last}" for c in "AC")

    first = 5
    for i, code in enumerate(accounts, start=first):
        ws[f"A{i}"] = code
        ws[f"B{i}"] = f'=_xlfn.XLOOKUP(A{i},{act_a},{act_b},"UNKNOWN ACCOUNT")'
        ws[f"C{i}"] = f"=_xlfn.XLOOKUP(A{i},{led_a},{led_b},0)"
        ws[f"D{i}"] = f"=_xlfn.XLOOKUP(A{i},{led_a},{led_c},0)"
        ws[f"E{i}"] = f"=_xlfn.XLOOKUP(A{i},{act_a},{act_tot},0)"
        ws[f"F{i}"] = f"=D{i}-E{i}"
        ws[f"G{i}"] = f"=_xlfn.XLOOKUP(A{i},{q_a},{q_c},0)"
        ws[f"H{i}"] = f"=ROUND(F{i}-G{i},2)"
        ws[f"I{i}"] = f'=IF(ABS(H{i})<0.005,"OK","CHECK")'
        for col in "DEFGH":
            ws[f"{col}{i}"].number_format = FMT_EUR
    last = first + len(accounts) - 1

    total_row = last + 1
    ws[f"A{total_row}"] = "Total"
    ws[f"A{total_row}"].font = FONT_BOLD
    ws[f"C{total_row}"] = f"=SUM(C{first}:C{last})"
    for col in "DEFGH":
        ws[f"{col}{total_row}"] = f"=SUM({col}{first}:{col}{last})"
        ws[f"{col}{total_row}"].number_format = FMT_EUR
    ws[f"I{total_row}"] = f'=IF(COUNTIF(I{first}:I{last},"CHECK")=0,"ALL OK","ISSUES")'
    for col in "ABCDEFGHI":
        ws[f"{col}{total_row}"].font = FONT_BOLD
        ws[f"{col}{total_row}"].border = THIN_TOP

    # Conditional formatting
    rng_f, rng_h, rng_i = f"F{first}:F{last}", f"H{first}:H{total_row}", f"I{first}:I{total_row}"
    ws.conditional_formatting.add(
        rng_f, FormulaRule(formula=[f"ABS(F{first})>=0.005"], fill=FILL_AMBER))
    ws.conditional_formatting.add(
        rng_h, FormulaRule(formula=[f"ABS(H{first})>=0.005"], fill=FILL_RED))
    ws.conditional_formatting.add(
        rng_i, CellIsRule(operator="equal", formula=['"CHECK"'], fill=FILL_RED))
    ws.conditional_formatting.add(
        rng_i, CellIsRule(operator="equal", formula=['"ISSUES"'], fill=FILL_RED))
    ws.conditional_formatting.add(
        rng_i, CellIsRule(operator="equal", formula=['"OK"'], fill=FILL_GREEN))
    ws.conditional_formatting.add(
        rng_i, CellIsRule(operator="equal", formula=['"ALL OK"'], fill=FILL_GREEN))
    ws.conditional_formatting.add(
        f"B{first}:B{last}",
        CellIsRule(operator="equal", formula=['"UNKNOWN ACCOUNT"'], fill=FILL_RED))

    legend = total_row + 2
    notes = [
        "Legend",
        "Amber 'Difference': ledger and warehouse differ – expected when rows were quarantined.",
        "Red 'Unexplained difference': ledger - warehouse - quarantine <> 0 → investigate.",
        "'UNKNOWN ACCOUNT': account exists in the ledger but not in the chart of accounts "
        "(DQ04) – the whole amount must sit in quarantine.",
    ]
    for k, note in enumerate(notes):
        ws[f"A{legend + k}"] = note
        ws[f"A{legend + k}"].font = FONT_BOLD if k == 0 else FONT_NOTE
    ws.freeze_panes = "C5"
    _widths(ws, {"A": 10, "B": 26, "C": 11, "D": 19, "E": 19, "F": 16, "G": 17, "H": 16,
                 "I": 10})


def write_data(ws: Worksheet, data: pd.DataFrame) -> int:
    """Write the flat fact table as an Excel Table and return the last row."""
    headers = ["Fiscal year", "Period", "Department", "Cost centre", "Cost centre name",
               "P&L category", "P&L group", "Account", "Account name", "Scenario", "Amount"]
    _header(ws, 1, headers)
    for i, rec in enumerate(data.itertuples(index=False), start=2):
        for j, value in enumerate(rec, start=1):
            ws.cell(row=i, column=j, value=value.item() if hasattr(value, "item") else value)
        ws.cell(row=i, column=11).number_format = FMT_EUR
    last = len(data) + 1
    table = Table(displayName="tblFinance", ref=f"A1:K{last}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)
    ws.freeze_panes = "A2"
    _widths(ws, {"A": 10, "B": 9, "C": 15, "D": 11, "E": 20, "F": 20, "G": 19, "H": 9,
                 "I": 24, "J": 10, "K": 15})
    return last


def write_summary(ws: Worksheet, data_last: int, departments: list[str]) -> None:
    """Write the formula-based budget vs. actual summary."""
    _title(ws, f"{COMPANY} – Budget vs. Actual summary",
           "All values are SUMIFS formulas on the Data sheet. Change the fiscal year in C4.")
    ws["B4"] = "Fiscal year:"
    ws["B4"].font = FONT_BOLD
    ws["C4"] = max(FISCAL_YEARS)
    ws["C4"].fill = FILL_INPUT
    ws["C4"].font = FONT_BOLD
    dv = DataValidation(type="list", formula1=f'"{",".join(str(y) for y in FISCAL_YEARS)}"',
                        allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("C4")

    rng = {k: f"Data!${c}$2:${c}${data_last}" for k, c in
           {"year": "A", "dept": "C", "cat": "F", "scen": "J", "amt": "K"}.items()}

    def sumifs(scenario: str, extra: str) -> str:
        return (f'SUMIFS({rng["amt"]},{rng["year"]},$C$4,{rng["scen"]},"{scenario}"{extra})')

    # Block 1: operating costs by department (expense accounts only)
    ws["B6"] = "Costs by department (COGS + OpEx)"
    ws["B6"].font = FONT_TITLE
    cols = ["Department", "Actual", "Budget", "Variance", "Variance %", "Forecast",
            "Assessment"]
    _header(ws, 7, cols, start_col=2)
    first = 8
    for i, dept in enumerate(departments, start=first):
        ws[f"B{i}"] = dept
        expense = f',{rng["dept"]},$B{i},{rng["cat"]},"<>Revenue"'
        ws[f"C{i}"] = f"={sumifs('Actual', expense)}"
        ws[f"D{i}"] = f"={sumifs('Budget', expense)}"
        ws[f"G{i}"] = f"={sumifs('Forecast', expense)}"
    last = first + len(departments) - 1
    total = last + 1
    ws[f"B{total}"] = "Total costs"
    for col in "CDG":
        ws[f"{col}{total}"] = f"=SUM({col}{first}:{col}{last})"
    for i in range(first, total + 1):
        ws[f"E{i}"] = f"=C{i}-D{i}"
        ws[f"F{i}"] = f"=IF(D{i}=0,\"\",E{i}/D{i})"
        ws[f"H{i}"] = f'=IF(E{i}>0,"Over budget","Within budget")'
        for col in "CDEG":
            ws[f"{col}{i}"].number_format = FMT_EUR0
        ws[f"F{i}"].number_format = FMT_PCT
    for col in "BCDEFGH":
        ws[f"{col}{total}"].font = FONT_BOLD
        ws[f"{col}{total}"].border = THIN_TOP
    ws.conditional_formatting.add(
        f"F{first}:F{total}", CellIsRule(operator="greaterThan", formula=["0.05"], fill=FILL_RED))
    ws.conditional_formatting.add(
        f"F{first}:F{total}",
        CellIsRule(operator="between", formula=["0.0001", "0.05"], fill=FILL_AMBER))
    ws.conditional_formatting.add(
        f"F{first}:F{total}", CellIsRule(operator="lessThanOrEqual", formula=["0"],
                                         fill=FILL_GREEN))

    # Block 2: P&L summary
    start = total + 3
    ws[f"B{start - 1}"] = "P&L summary"
    ws[f"B{start - 1}"].font = FONT_TITLE
    _header(ws, start, ["Line", "Actual", "Budget", "Variance", "Variance %", "Forecast"],
            start_col=2)
    lines = [
        ("Revenue", "Revenue", False),
        ("Cost of Goods Sold", "Cost of Goods Sold", False),
        ("Gross profit", None, True),
        ("Gross margin %", None, True),
        ("Operating Expenses", "Operating Expenses", False),
        ("EBIT", None, True),
        ("EBIT margin %", None, True),
    ]
    r = {name: start + 1 + k for k, (name, _, _) in enumerate(lines)}
    for name, category, is_calc in lines:
        row = r[name]
        ws[f"B{row}"] = name
        for col, scen in (("C", "Actual"), ("D", "Budget"), ("G", "Forecast")):
            if not is_calc:
                cat_filter = "," + rng["cat"] + ',"' + str(category) + '"'
                ws[f"{col}{row}"] = "=" + sumifs(scen, cat_filter)
            elif name == "Gross profit":
                ws[f"{col}{row}"] = f"={col}{r['Revenue']}-{col}{r['Cost of Goods Sold']}"
            elif name == "Gross margin %":
                ws[f"{col}{row}"] = f"=IF({col}{r['Revenue']}=0,\"\"," \
                                    f"{col}{r['Gross profit']}/{col}{r['Revenue']})"
            elif name == "EBIT":
                ws[f"{col}{row}"] = f"={col}{r['Gross profit']}-{col}{r['Operating Expenses']}"
            elif name == "EBIT margin %":
                ws[f"{col}{row}"] = f"=IF({col}{r['Revenue']}=0,\"\"," \
                                    f"{col}{r['EBIT']}/{col}{r['Revenue']})"
        is_pct = name.endswith("%")
        if is_pct:
            ws[f"E{row}"] = f"=(C{row}-D{row})*100"
            ws[f"E{row}"].number_format = '0.0" pp";[Red]-0.0" pp"'
            ws[f"F{row}"] = "n/a"
        else:
            ws[f"E{row}"] = f"=C{row}-D{row}"
            ws[f"F{row}"] = f"=IF(D{row}=0,\"\",E{row}/D{row})"
            ws[f"F{row}"].number_format = FMT_PCT
        for col in "CDEG":
            if col != "E" or not is_pct:
                ws[f"{col}{row}"].number_format = FMT_PCT if is_pct else FMT_EUR0
        if is_calc:
            for col in "BCDEFG":
                ws[f"{col}{row}"].font = FONT_BOLD
    ws[f"B{r['EBIT margin %'] + 2}"] = (
        "Note: for cost lines a positive variance is adverse; for revenue and profit lines "
        "a positive variance is favourable. Margin variances are shown in percentage points.")
    ws[f"B{r['EBIT margin %'] + 2}"].font = FONT_NOTE
    _widths(ws, {"A": 2, "B": 34, "C": 15, "D": 15, "E": 15, "F": 12, "G": 15, "H": 15})


def write_readme(ws: Worksheet) -> None:
    """Write the README sheet."""
    rows = [
        (f"{COMPANY} – Controlling reconciliation workbook", FONT_TITLE),
        ("Generated by `make excel` (src/cockpit/excel_workbook.py). Do not edit by hand – "
         "regenerate instead.", FONT_NOTE),
        ("", None),
        ("Purpose", FONT_BOLD),
        ("Prove that the numbers in the data warehouse / Power BI are complete and correct "
         "before anyone discusses variances.", None),
        ("", None),
        ("Sheets", FONT_BOLD),
        ("Summary – budget vs. actual by department and a P&L summary (SUMIFS on Data). "
         "Select the fiscal year in cell C4.", None),
        ("Reconciliation – per account: ledger total (raw CSV) vs. warehouse total (SQL), "
         "looked up with XLOOKUP.", None),
        ("Actuals – warehouse actuals by account and month (source for Reconciliation).", None),
        ("Ledger_Totals – totals computed directly from data/raw/gl_actuals.csv with pandas "
         "(independent of SQL).", None),
        ("Quarantine – amounts rejected by the data-quality checks (fact_finance_rejected).",
         None),
        ("Data – flat fact table (Excel Table 'tblFinance'); source for SUMIFS and the "
         "pivot table (docs/excel_pivot_steps.md).", None),
        ("", None),
        ("Checks", FONT_BOLD),
        ("1. Completeness: Ledger total = Warehouse total + Quarantined, for every account.",
         None),
        ("2. Unknown accounts: accounts in the ledger but not in the chart of accounts show "
         "'UNKNOWN ACCOUNT' and must be 100% quarantined.", None),
        ("3. Status column: OK when the unexplained difference is below 0.005 EUR; "
         "the total row shows ALL OK / ISSUES.", None),
        ("4. Formula-based summary: all Summary values are formulas, so they can be traced "
         "and audited.", None),
        ("", None),
        ("Colour code", FONT_BOLD),
        ("Yellow cell = input. Green = OK / within budget. Amber = explained difference or "
         "up to 5% over budget. Red = unexplained difference or more than 5% over budget.",
         None),
        ("", None),
        ("Pivot table", FONT_BOLD),
        ("openpyxl cannot create native pivot tables. Build it in 2 minutes from tblFinance "
         "– see docs/excel_pivot_steps.md.", None),
    ]
    for i, (text, font) in enumerate(rows, start=1):
        ws[f"A{i}"] = text
        if font is not None:
            ws[f"A{i}"].font = font
        ws[f"A{i}"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 120


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def build_workbook(output: Path = OUTPUT_PATH, db_path: Path = WAREHOUSE_PATH,
                   raw_dir: Path = RAW_DIR) -> Path:
    """Create the workbook and return its path."""
    frames = load_frames(db_path, raw_dir)
    wb = Workbook()
    ws_readme = wb.active
    ws_readme.title = "README"
    ws_summary = wb.create_sheet("Summary")
    ws_recon = wb.create_sheet("Reconciliation")
    ws_act = wb.create_sheet("Actuals")
    ws_led = wb.create_sheet("Ledger_Totals")
    ws_q = wb.create_sheet("Quarantine")
    ws_data = wb.create_sheet("Data")

    write_readme(ws_readme)
    act = write_actuals(ws_act, frames["actuals"])
    ledger_last = write_simple_table(
        ws_led, "Ledger totals by account (raw CSV, all rows)",
        "Source: data/raw/gl_actuals.csv read with pandas – independent of the SQL pipeline",
        frames["ledger"], ["Account", "Rows booked", "Ledger total"], money_cols={3})
    quarantine_last = write_simple_table(
        ws_q, "Quarantined actuals by account",
        "Source: fact_finance_rejected (rows failing ERROR-severity DQ checks)",
        frames["quarantine"], ["Account", "Rows rejected", "Amount rejected"], money_cols={3})
    data_last = write_data(ws_data, frames["data"])
    accounts = sorted(
        set(frames["ledger"]["account_code"]) | set(frames["actuals"]["account_code"])
    )
    write_reconciliation(ws_recon, accounts, act, ledger_last, quarantine_last)
    departments = sorted(frames["data"]["department"].unique())
    write_summary(ws_summary, data_last, departments)

    ws_readme.sheet_properties.tabColor = NAVY
    ws_summary.sheet_properties.tabColor = "2E75B6"
    ws_recon.sheet_properties.tabColor = "C00000"
    wb.active = 1  # open on Summary
    wb.calculation.fullCalcOnLoad = True
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return output


def main() -> None:
    """CLI entry point."""
    path = build_workbook()
    print(f"Workbook written: {path.relative_to(path.parents[1])}")


if __name__ == "__main__":
    main()
