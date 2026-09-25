"""Step 2 – the star schema reconciles to the clean raw data and is structurally sound."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd


def test_actual_total_equals_clean_raw_total(
    con: duckdb.DuckDBPyConnection, clean_gl: pd.DataFrame
) -> None:
    fact_total = con.execute("SELECT SUM(amount) FROM fact_finance WHERE scenario_key = 1"
                             ).fetchone()[0]
    assert fact_total == Decimal(str(round(clean_gl["amount"].sum(), 2)))


def test_actuals_reconcile_per_account_and_month(
    con: duckdb.DuckDBPyConnection, clean_gl: pd.DataFrame
) -> None:
    fact = con.execute(
        """
        SELECT d.period, a.account_code, c.cost_centre_code, CAST(f.amount AS DOUBLE) AS amount
        FROM fact_finance f
        JOIN dim_date d ON d.date_key = f.date_key
        JOIN dim_account a ON a.account_key = f.account_key
        JOIN dim_cost_centre c ON c.cost_centre_key = f.cost_centre_key
        WHERE f.scenario_key = 1
        """
    ).df()
    raw = (clean_gl.groupby(["period", "account_code", "cost_centre_code"], as_index=False)
           ["amount"].sum())
    merged = raw.merge(fact, on=["period", "account_code", "cost_centre_code"],
                       how="outer", suffixes=("_raw", "_fact"), indicator=True)
    assert (merged["_merge"] == "both").all()
    assert (merged["amount_raw"] - merged["amount_fact"]).abs().max() < 0.005


def test_rejected_total_equals_injected_rows(
    con: duckdb.DuckDBPyConnection, raw_dir: Path, injected: dict
) -> None:
    gl = pd.read_csv(raw_dir / "gl_actuals.csv")
    bad = gl[gl["entry_id"].isin({i["entry_id"] for i in injected["issues"]})]
    rejected = con.execute(
        "SELECT CAST(SUM(amount) AS DOUBLE) FROM fact_finance_rejected WHERE scenario = 'Actual'"
    ).fetchone()[0]
    assert abs(rejected - bad["amount"].sum()) < 0.005


def test_budget_and_forecast_fully_loaded(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> None:
    for key, file in ((2, "budget.csv"), (3, "forecast.csv")):
        raw = pd.read_csv(raw_dir / file)["amount"].sum()
        fact = con.execute("SELECT CAST(SUM(amount) AS DOUBLE) FROM fact_finance "
                           "WHERE scenario_key = ?", [key]).fetchone()[0]
        assert abs(raw - fact) < 0.01


def test_fact_grain_is_unique(con: duckdb.DuckDBPyConnection) -> None:
    dupes = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT date_key, account_key, cost_centre_key, scenario_key
            FROM fact_finance GROUP BY ALL HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert dupes == 0


def test_no_orphan_foreign_keys(con: duckdb.DuckDBPyConnection) -> None:
    for fk, dim, pk in (("date_key", "dim_date", "date_key"),
                        ("account_key", "dim_account", "account_key"),
                        ("cost_centre_key", "dim_cost_centre", "cost_centre_key"),
                        ("scenario_key", "dim_scenario", "scenario_key")):
        orphans = con.execute(
            f"SELECT COUNT(*) FROM fact_finance f LEFT JOIN {dim} d ON d.{pk} = f.{fk} "
            f"WHERE d.{pk} IS NULL").fetchone()[0]
        assert orphans == 0, fk


def test_dim_date_is_contiguous_full_years(con: duckdb.DuckDBPyConnection) -> None:
    lo, hi, n, distinct = con.execute(
        "SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT date) FROM dim_date").fetchone()
    assert str(lo) == "2023-01-01" and str(hi) == "2025-12-31"
    assert n == distinct == 1096  # 2024 is a leap year


def test_dimension_keys_unique(con: duckdb.DuckDBPyConnection) -> None:
    for dim, pk in (("dim_account", "account_key"), ("dim_cost_centre", "cost_centre_key"),
                    ("dim_scenario", "scenario_key"), ("dim_date", "date_key")):
        n, distinct = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT {pk}) FROM {dim}").fetchone()
        assert n == distinct, dim
