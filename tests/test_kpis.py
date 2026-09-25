"""Step 2/6 – KPI values from SQL match hand-calculated expectations.

Part A runs the real SQL pipeline on a tiny dataset where every number can be checked
with a pocket calculator. Part B cross-checks the full dataset against an independent
pandas calculation from the clean raw ledger.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from cockpit.warehouse import build

# --------------------------------------------------------------------------------------
# Part A – hand-calculated mini dataset
# --------------------------------------------------------------------------------------
#
# FY2024 actual : revenue 1,000 | COGS 400 | personnel 200 | marketing 100
# FY2025 actual : revenue 600 + 600 = 1,200 | COGS 500 | personnel 250 | marketing 180
#                 + 1 negative revenue row (-50)  -> rejected (DQ06)
#                 + 1 duplicate of the COGS row  -> rejected (DQ01)
# FY2025 budget : revenue 1,000 | COGS 450 | personnel 250 | marketing 100
# FY2025 fcst   : revenue 1,100 | COGS 500 | personnel 250 | marketing 180
#
# Hand calculation FY2025 actual:
#   gross profit = 1,200 - 500 = 700        gross margin = 700 / 1,200 = 58.33 %
#   opex = 250 + 180 = 430                  EBIT = 700 - 430 = 270
#   EBIT margin = 270 / 1,200 = 22.50 %
# FY2025 budget: GP = 550 (55.00 %), EBIT = 550 - 350 = 200 (20.00 %)
# YoY revenue = (1,200 - 1,000) / 1,000 = +20.00 %; YoY COGS = +25.00 %
# Marketing dept expense variance = (180 - 100) / 100 = +80.00 % (adverse)
# Sales dept income variance = (1,200 - 1,000) / 1,000 = +20.00 % (favourable)
# Revenue forecast accuracy = 1 - |1,200 - 1,100| / 1,200 = 91.67 %
#   (two revenue rows sit in the same month/account/cc cell -> WAPE on the 1,200 total)

COA = """account_code,account_name,pnl_group,pnl_category,pnl_group_sort,sign
4000,Product Revenue,Revenue,Revenue,1,1
5000,Material Costs,Cost of Goods Sold,Cost of Goods Sold,2,-1
6000,Salaries & Wages,Personnel Costs,Operating Expenses,3,-1
6100,Advertising,Marketing,Operating Expenses,4,-1
"""
CCS = """cost_centre_code,cost_centre_name,department,region,manager
CC100,Sales DACH,Sales,DACH,A
CC300,Marketing DACH,Marketing,DACH,B
"""
GL = """entry_id,document_ref,posting_date,period,account_code,cost_centre_code,currency,amount,text
JE01,D01,2024-01-10,2024-01,4000,CC100,EUR,1000.00,x
JE02,D02,2024-01-10,2024-01,5000,CC100,EUR,400.00,x
JE03,D03,2024-01-31,2024-01,6000,CC100,EUR,200.00,x
JE04,D04,2024-01-15,2024-01,6100,CC300,EUR,100.00,x
JE05,D05,2025-01-10,2025-01,4000,CC100,EUR,600.00,x
JE06,D06,2025-01-20,2025-01,4000,CC100,EUR,600.00,x
JE07,D07,2025-01-10,2025-01,5000,CC100,EUR,500.00,x
JE08,D08,2025-01-31,2025-01,6000,CC100,EUR,250.00,x
JE09,D09,2025-01-15,2025-01,6100,CC300,EUR,180.00,x
JE10,D10,2025-01-22,2025-01,4000,CC100,EUR,-50.00,sign error
JE11,D07,2025-01-10,2025-01,5000,CC100,EUR,500.00,duplicate
"""
PLAN = """period,account_code,cost_centre_code,amount
2024-01,4000,CC100,1000.00
2024-01,5000,CC100,400.00
2024-01,6000,CC100,200.00
2024-01,6100,CC300,100.00
2025-01,4000,CC100,{rev}
2025-01,5000,CC100,{cogs}
2025-01,6000,CC100,250.00
2025-01,6100,CC300,{mkt}
"""


@pytest.fixture(scope="module")
def mini(tmp_path_factory: pytest.TempPathFactory) -> duckdb.DuckDBPyConnection:
    """Warehouse built from the hand-calculated mini dataset."""
    raw = tmp_path_factory.mktemp("mini")
    (raw / "chart_of_accounts.csv").write_text(COA)
    (raw / "cost_centres.csv").write_text(CCS)
    (raw / "gl_actuals.csv").write_text(GL)
    (raw / "budget.csv").write_text(PLAN.format(rev="1000.00", cogs="450.00", mkt="100.00"))
    (raw / "forecast.csv").write_text(PLAN.format(rev="1100.00", cogs="500.00", mkt="180.00"))
    return build(raw_dir=raw, db_path=":memory:")


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> tuple:
    row = con.execute(sql).fetchone()
    assert row is not None
    return tuple(float(v) if v is not None else None for v in row)


def test_mini_rejects_exactly_the_two_bad_rows(mini: duckdb.DuckDBPyConnection) -> None:
    rows = dict(mini.execute(
        "SELECT record_key, reject_check_id FROM fact_finance_rejected").fetchall())
    assert rows == {"JE10": "DQ06", "JE11": "DQ01"}


def test_mini_margins_actual(mini: duckdb.DuckDBPyConnection) -> None:
    got = _one(mini, "SELECT revenue, cogs, gross_profit, gross_margin_pct, opex, ebit, "
                     "ebit_margin_pct FROM v_margins WHERE fiscal_year = 2025 "
                     "AND scenario = 'Actual'")
    assert got == (1200.0, 500.0, 700.0, 58.33, 430.0, 270.0, 22.5)


def test_mini_margins_budget(mini: duckdb.DuckDBPyConnection) -> None:
    got = _one(mini, "SELECT gross_margin_pct, ebit, ebit_margin_pct FROM v_margins "
                     "WHERE fiscal_year = 2025 AND scenario = 'Budget'")
    assert got == (55.0, 200.0, 20.0)


def test_mini_yoy(mini: duckdb.DuckDBPyConnection) -> None:
    yoy = dict(mini.execute(
        "SELECT pnl_group, yoy_pct FROM v_yoy_growth WHERE fiscal_year = 2025").fetchall())
    assert float(yoy["Revenue"]) == 20.0
    assert float(yoy["Cost of Goods Sold"]) == 25.0


def test_mini_variance_by_department(mini: duckdb.DuckDBPyConnection) -> None:
    rows = {(d, t): (float(v), float(p), a) for d, t, v, p, a in mini.execute(
        "SELECT department, account_type, variance, variance_pct, assessment "
        "FROM v_bva_department WHERE fiscal_year = 2025").fetchall()}
    assert rows[("Marketing", "Expense")] == (80.0, 80.0, "Adverse")
    assert rows[("Sales", "Income")] == (200.0, 20.0, "Favourable")


def test_mini_top_overrun_and_ytd(mini: duckdb.DuckDBPyConnection) -> None:
    top = mini.execute("SELECT account, overrun, overrun_pct FROM v_top5_cost_overruns "
                       "WHERE fiscal_year = 2025 AND overrun_rank = 1").fetchone()
    assert top[0] == "6100 Advertising" and float(top[1]) == 80.0 and float(top[2]) == 80.0
    ytd = _one(mini, "SELECT revenue_actual_ytd, ebit_actual_ytd, ebit_budget_ytd "
                     "FROM v_running_ytd WHERE period = '2025-01'")
    assert ytd == (1200.0, 270.0, 200.0)


def test_mini_forecast_accuracy(mini: duckdb.DuckDBPyConnection) -> None:
    acc = _one(mini, "SELECT forecast_accuracy_pct FROM v_forecast_accuracy "
                     "WHERE fiscal_year = 2025 AND pnl_group = 'Revenue'")
    assert acc == (91.67,)


# --------------------------------------------------------------------------------------
# Part B – full dataset vs. independent pandas calculation
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pnl_pandas(clean_gl: pd.DataFrame, raw_dir: Path) -> pd.DataFrame:
    """Revenue / COGS / OpEx per year computed with pandas from the clean raw ledger."""
    coa = pd.read_csv(raw_dir / "chart_of_accounts.csv", dtype={"account_code": str})
    df = clean_gl.merge(coa, on="account_code")
    df["year"] = df["period"].str[:4].astype(int)
    return df.pivot_table(index="year", columns="pnl_category", values="amount", aggfunc="sum")


@pytest.mark.parametrize("year", [2023, 2024, 2025])
def test_full_margins_match_pandas(
    con: duckdb.DuckDBPyConnection, pnl_pandas: pd.DataFrame, year: int
) -> None:
    p = pnl_pandas.loc[year]
    revenue, cogs, opex = p["Revenue"], p["Cost of Goods Sold"], p["Operating Expenses"]
    expected_gm = round(100 * (revenue - cogs) / revenue, 2)
    expected_ebit = round(100 * (revenue - cogs - opex) / revenue, 2)
    got = _one(con, f"SELECT revenue, gross_margin_pct, ebit_margin_pct FROM v_margins "
                    f"WHERE fiscal_year = {year} AND scenario = 'Actual'")
    assert got[0] == pytest.approx(revenue, abs=0.01)
    assert got[1] == pytest.approx(expected_gm, abs=0.011)
    assert got[2] == pytest.approx(expected_ebit, abs=0.011)


def test_story_marketing_benelux_over_budget_every_year(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute("SELECT fiscal_year, cost_centre_code, variance_pct FROM "
                       "v_bva_cost_centre WHERE overrun_rank = 1").fetchall()
    assert {r[1] for r in rows} == {"CC310"}
    assert all(float(r[2]) > 10 for r in rows)
