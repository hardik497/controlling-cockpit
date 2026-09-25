"""Step 2 – every injected issue is detected by the matching check, with no false positives."""

from __future__ import annotations

import duckdb
import pytest

ISSUE_TO_CHECK = {
    "duplicate_booking": "DQ01",
    "missing_cost_centre": "DQ02",
    "unknown_account": "DQ04",
    "negative_revenue": "DQ06",
    "wrong_period": "DQ08",
}


@pytest.mark.parametrize(("issue_type", "check_id"), sorted(ISSUE_TO_CHECK.items()))
def test_each_injected_issue_is_detected(
    con: duckdb.DuckDBPyConnection, injected: dict, issue_type: str, check_id: str
) -> None:
    expected = {i["entry_id"] for i in injected["issues"] if i["issue_type"] == issue_type}
    flagged = {r[0] for r in con.execute(
        "SELECT record_key FROM dq_row_flags WHERE check_id = ?", [check_id]).fetchall()}
    assert expected, f"no {issue_type} issues were injected"
    assert flagged == expected, (
        f"{check_id}: missed {len(expected - flagged)}, false positives {len(flagged - expected)}")


def test_no_false_positives_overall(con: duckdb.DuckDBPyConnection, injected: dict) -> None:
    injected_ids = {i["entry_id"] for i in injected["issues"]}
    flagged = {r[0] for r in con.execute(
        "SELECT DISTINCT record_key FROM dq_row_flags WHERE source_table = 'stg_gl_actuals'"
    ).fetchall()}
    assert flagged == injected_ids


def test_dq_results_counts_match_log(con: duckdb.DuckDBPyConnection, injected: dict) -> None:
    rows = dict(con.execute("SELECT check_id, rows_affected FROM dq_results").fetchall())
    for issue_type, check_id in ISSUE_TO_CHECK.items():
        assert rows[check_id] == injected["issue_counts"][issue_type]


def test_dq_results_structure(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute("SELECT * FROM dq_results").df()
    assert {"check_name", "severity", "rows_affected", "sample_keys"} <= set(df.columns)
    assert df["check_id"].is_unique
    assert set(df["status"]) <= {"PASS", "FAIL", "WARN"}
    # a failing check always carries evidence
    assert df.loc[df["rows_affected"] > 0, "sample_keys"].notna().all()


def test_reconciliation_checks_pass(con: duckdb.DuckDBPyConnection) -> None:
    status = dict(con.execute(
        "SELECT check_id, status FROM dq_results WHERE check_category = 'Reconciliation'"
    ).fetchall())
    assert status == {"DQ16": "PASS", "DQ17": "PASS", "DQ18": "PASS", "DQ19": "PASS"}


def test_rejected_rows_are_quarantined_not_dropped(
    con: duckdb.DuckDBPyConnection, injected: dict
) -> None:
    rejected = {r[0] for r in con.execute(
        "SELECT record_key FROM fact_finance_rejected WHERE scenario = 'Actual'").fetchall()}
    assert rejected == {i["entry_id"] for i in injected["issues"]}
    reasons = con.execute(
        "SELECT COUNT(*) FROM fact_finance_rejected WHERE reject_reason IS NULL").fetchone()[0]
    assert reasons == 0
