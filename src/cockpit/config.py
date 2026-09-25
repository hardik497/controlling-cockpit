"""Central paths and constants shared by all pipeline steps."""

from __future__ import annotations

from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
MODEL_DIR: Path = DATA_DIR / "model"
SAMPLE_DIR: Path = DATA_DIR / "sample"
SQL_DIR: Path = ROOT / "sql"
EXCEL_DIR: Path = ROOT / "excel"
WAREHOUSE_PATH: Path = DATA_DIR / "warehouse.duckdb"
INJECTED_ISSUES_PATH: Path = RAW_DIR / "_injected_issues.json"

SEED: int = 42
FISCAL_YEARS: tuple[int, ...] = (2023, 2024, 2025)
COMPANY: str = "Nordwerk GmbH"
CURRENCY: str = "EUR"

# Ordered list of SQL scripts that build the warehouse.
BUILD_SCRIPTS: tuple[str, ...] = (
    "01_staging.sql",
    "02_data_quality.sql",
    "03_star_schema.sql",
)
ANALYSIS_SCRIPT: str = "04_analysis.sql"

# Star-schema tables exported for Power BI.
MODEL_TABLES: tuple[str, ...] = (
    "dim_date",
    "dim_account",
    "dim_cost_centre",
    "dim_scenario",
    "fact_finance",
    "fact_finance_rejected",
    "dq_results",
)
