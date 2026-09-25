"""Step 1 – the synthetic data is reproducible, realistic in size and logs its issues."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from cockpit.generate_data import ISSUE_COUNTS, generate

FILES = ["chart_of_accounts.csv", "cost_centres.csv", "gl_actuals.csv", "budget.csv",
         "forecast.csv", "_injected_issues.json"]


def _digest(folder: Path) -> dict[str, str]:
    return {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in FILES}


def test_generation_is_reproducible(raw_dir: Path, tmp_path: Path) -> None:
    again = tmp_path / "again"
    generate(again)
    assert _digest(raw_dir) == _digest(again)


def test_different_seed_gives_different_data(raw_dir: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    generate(other, seed=7)
    assert _digest(raw_dir)["gl_actuals.csv"] != _digest(other)["gl_actuals.csv"]


def test_volume_and_master_data(raw_dir: Path) -> None:
    gl = pd.read_csv(raw_dir / "gl_actuals.csv")
    coa = pd.read_csv(raw_dir / "chart_of_accounts.csv")
    ccs = pd.read_csv(raw_dir / "cost_centres.csv")
    assert 45_000 <= len(gl) <= 55_000
    assert 28 <= len(coa) <= 35
    assert len(ccs) == 8
    assert set(ccs["department"]) == {"Sales", "Operations", "Marketing", "Administration"}
    assert set(ccs["region"]) == {"DACH", "Benelux", "Nordics"}
    assert gl["entry_id"].is_unique


def test_issue_log_matches_config(injected: dict) -> None:
    assert injected["issue_counts"] == ISSUE_COUNTS
    assert len(injected["issues"]) == sum(ISSUE_COUNTS.values())
    assert 1.5 <= injected["issue_rate_pct"] <= 2.5
    # one issue per row -> detection can be verified 1:1
    ids = [i["entry_id"] for i in injected["issues"]]
    assert len(ids) == len(set(ids))


def test_plan_covers_all_three_years(raw_dir: Path) -> None:
    budget = pd.read_csv(raw_dir / "budget.csv")
    years = budget["period"].str[:4].astype(int)
    assert set(years) == {2023, 2024, 2025}
    assert (budget["amount"] > 0).all()
