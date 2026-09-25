"""Build the DuckDB warehouse, run data-quality checks and export the star schema.

Usage::

    python -m cockpit.warehouse build      # staging -> DQ -> star schema -> export
    python -m cockpit.warehouse quality    # print the dq_results report
    python -m cockpit.warehouse analysis   # print the analytical queries of 04_analysis.sql
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd

from cockpit.config import (
    ANALYSIS_SCRIPT,
    BUILD_SCRIPTS,
    MODEL_DIR,
    MODEL_TABLES,
    RAW_DIR,
    SQL_DIR,
    WAREHOUSE_PATH,
)

_VIEW_PATTERN = re.compile(r"CREATE OR REPLACE VIEW\s+(\w+)", re.IGNORECASE)


def render_sql(path: Path, raw_dir: Path) -> str:
    """Read a SQL file and substitute the ``${RAW_DIR}`` placeholder."""
    return path.read_text(encoding="utf-8").replace("${RAW_DIR}", raw_dir.as_posix())


def connect(db_path: Path | str = WAREHOUSE_PATH) -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB warehouse. Pass ``":memory:"`` for an in-memory DB."""
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def build(
    raw_dir: Path = RAW_DIR,
    db_path: Path | str = WAREHOUSE_PATH,
    with_analysis: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Run all build scripts (and optionally the analysis views) and return the connection."""
    if isinstance(db_path, Path) and db_path.exists():
        db_path.unlink()  # always build from a clean state
    con = connect(db_path)
    scripts = [*BUILD_SCRIPTS, ANALYSIS_SCRIPT] if with_analysis else list(BUILD_SCRIPTS)
    for script in scripts:
        con.execute(render_sql(SQL_DIR / script, raw_dir))
    return con


def export_model(con: duckdb.DuckDBPyConnection, out_dir: Path = MODEL_DIR) -> list[Path]:
    """Export every star-schema table to CSV and Parquet for Power BI / Excel."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table in MODEL_TABLES:
        csv_path = out_dir / f"{table}.csv"
        parquet_path = out_dir / f"{table}.parquet"
        con.execute(
            f"COPY (SELECT * FROM {table}) TO '{csv_path.as_posix()}' (HEADER, DELIMITER ',')"
        )
        con.execute(f"COPY (SELECT * FROM {table}) TO '{parquet_path.as_posix()}' (FORMAT PARQUET)")
        written += [csv_path, parquet_path]
    return written


def dq_report(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return the data-quality results ordered by check id."""
    return con.execute(
        """
        SELECT check_id, check_name, severity, status, rows_checked, rows_affected,
               pct_affected, amount_affected, COALESCE(sample_keys, '') AS sample_keys
        FROM dq_results
        ORDER BY check_id
        """
    ).df()


def analysis_views() -> list[str]:
    """Return the names of the analytical views defined in 04_analysis.sql (in file order)."""
    return _VIEW_PATTERN.findall((SQL_DIR / ANALYSIS_SCRIPT).read_text(encoding="utf-8"))


def _print_frame(title: str, frame: pd.DataFrame) -> None:
    print(f"\n=== {title} " + "=" * max(0, 80 - len(title)))
    with pd.option_context("display.max_columns", 20, "display.width", 200,
                           "display.max_colwidth", 60):
        print(frame.to_string(index=False))


def cmd_build() -> int:
    """Build the warehouse and export the model."""
    con = build()
    files = export_model(con)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in MODEL_TABLES}
    print(f"Warehouse built: {WAREHOUSE_PATH.relative_to(WAREHOUSE_PATH.parents[1])}")
    for table, n in counts.items():
        print(f"  {table:<24} {n:>8,} rows")
    print(f"Exported {len(files)} files to {MODEL_DIR.name}/")
    con.close()
    return 0


def cmd_quality() -> int:
    """Print the DQ report; fail (exit 1) if any reconciliation check fails."""
    con = connect(WAREHOUSE_PATH)
    report = dq_report(con)
    _print_frame("Data-quality results", report)
    failed_recon = report[report["check_id"].isin(["DQ16", "DQ17", "DQ18", "DQ19"])
                          & (report["status"] != "PASS")]
    summary = report.groupby("status")["check_id"].count().to_dict()
    print(f"\nSummary: {summary}")
    quarantined = con.execute("SELECT COUNT(*) FROM fact_finance_rejected").fetchone()[0]
    print(f"Rows quarantined: {quarantined:,}")
    con.close()
    if not failed_recon.empty:
        print("RECONCILIATION FAILED – totals do not tie out.", file=sys.stderr)
        return 1
    print("Reconciliation checks: all PASS – every ledger euro is loaded or quarantined.")
    return 0


def cmd_analysis() -> int:
    """Print every analytical view."""
    con = connect(WAREHOUSE_PATH)
    for view in analysis_views():
        _print_frame(view, con.execute(f"SELECT * FROM {view}").df().head(15))
    con.close()
    return 0


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Controlling cockpit warehouse")
    parser.add_argument("command", choices=["build", "quality", "analysis"])
    args = parser.parse_args()
    handlers = {"build": cmd_build, "quality": cmd_quality, "analysis": cmd_analysis}
    sys.exit(handlers[args.command]())


if __name__ == "__main__":
    main()
