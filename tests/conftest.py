"""Shared fixtures: generate data and build a warehouse in a temp dir (never touches data/)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from cockpit.generate_data import generate
from cockpit.warehouse import build


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Freshly generated raw data (default seed)."""
    out = tmp_path_factory.mktemp("raw")
    generate(out)
    return out


@pytest.fixture(scope="session")
def db_path(raw_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fully built warehouse file (staging, DQ, star schema, analysis views)."""
    path = tmp_path_factory.mktemp("wh") / "warehouse.duckdb"
    build(raw_dir=raw_dir, db_path=path).close()
    return path


@pytest.fixture(scope="session")
def con(db_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """Read-only connection to the built warehouse."""
    connection = duckdb.connect(str(db_path), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def injected(raw_dir: Path) -> dict:
    """The injected-issues log written by the generator."""
    return json.loads((raw_dir / "_injected_issues.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def clean_gl(raw_dir: Path, injected: dict) -> pd.DataFrame:
    """Raw ledger minus every injected issue row = the 'truth' the warehouse must match."""
    gl = pd.read_csv(raw_dir / "gl_actuals.csv", dtype={"account_code": str})
    bad = {i["entry_id"] for i in injected["issues"]}
    return gl[~gl["entry_id"].isin(bad)].copy()
