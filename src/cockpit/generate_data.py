"""Generate reproducible synthetic controlling data for the fictional Nordwerk GmbH.

The generator produces:

* ``chart_of_accounts.csv`` – ~30 P&L accounts with a two-level hierarchy.
* ``cost_centres.csv``      – 8 cost centres across 4 departments and 3 regions.
* ``gl_actuals.csv``        – transaction-level general-ledger postings (~50k rows).
* ``budget.csv``            – monthly budget per account and cost centre.
* ``forecast.csv``          – latest rolling forecast per account and cost centre.
* ``_injected_issues.json`` – exact log of every deliberately injected data-quality issue.

Sign convention in the raw files: amounts are stored in their *natural* sign, i.e.
revenue and costs are both positive. The P&L sign lives in the chart of accounts
(``sign`` = +1 for income, -1 for expenses) and is applied in the semantic layer.

Run with ``python -m cockpit.generate_data``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from cockpit.config import COMPANY, CURRENCY, FISCAL_YEARS, RAW_DIR, SAMPLE_DIR, SEED

# --------------------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------------------

PNL_GROUPS: dict[str, dict[str, object]] = {
    # pnl_group: category, sort order, sign
    "Revenue": {"category": "Revenue", "sort": 1, "sign": 1},
    "Cost of Goods Sold": {"category": "Cost of Goods Sold", "sort": 2, "sign": -1},
    "Personnel Costs": {"category": "Operating Expenses", "sort": 3, "sign": -1},
    "Marketing": {"category": "Operating Expenses", "sort": 4, "sign": -1},
    "IT": {"category": "Operating Expenses", "sort": 5, "sign": -1},
    "Rent": {"category": "Operating Expenses", "sort": 6, "sign": -1},
    "Travel": {"category": "Operating Expenses", "sort": 7, "sign": -1},
    "Depreciation": {"category": "Operating Expenses", "sort": 8, "sign": -1},
    "Other OpEx": {"category": "Operating Expenses", "sort": 9, "sign": -1},
}


@dataclass(frozen=True)
class Account:
    """A general-ledger account with its annual base budget (EUR, FY2023)."""

    code: str
    name: str
    group: str
    annual_base: float
    tx_per_month: float  # mean number of GL postings per month and cost centre
    text: str  # typical posting text


ACCOUNTS: tuple[Account, ...] = (
    Account("4000", "Product Revenue", "Revenue", 40_000_000, 60, "Customer invoice"),
    Account("4010", "Service Revenue", "Revenue", 12_000_000, 45, "Service invoice"),
    Account("4020", "Licence Revenue", "Revenue", 6_000_000, 20, "Licence invoice"),
    Account("4090", "Other Operating Income", "Revenue", 1_000_000, 6, "Other income"),
    Account("5000", "Material Costs", "Cost of Goods Sold", 17_500_000, 45, "Supplier invoice"),
    Account("5010", "Purchased Services", "Cost of Goods Sold", 5_000_000, 25, "Subcontractor"),
    Account("5020", "Freight & Logistics", "Cost of Goods Sold", 2_500_000, 30, "Freight invoice"),
    Account("6000", "Salaries & Wages", "Personnel Costs", 11_000_000, 2, "Payroll run"),
    Account("6010", "Social Security", "Personnel Costs", 2_300_000, 1, "Social security"),
    Account("6020", "Bonuses", "Personnel Costs", 1_200_000, 1, "Bonus accrual"),
    Account("6030", "Training", "Personnel Costs", 400_000, 2, "Training invoice"),
    Account("6040", "Temporary Staff", "Personnel Costs", 600_000, 2, "Agency staff"),
    Account("6100", "Advertising", "Marketing", 1_800_000, 12, "Media booking"),
    Account("6110", "Trade Fairs & Events", "Marketing", 900_000, 6, "Event invoice"),
    Account("6120", "Agency Fees", "Marketing", 700_000, 4, "Agency invoice"),
    Account("6130", "Digital Marketing", "Marketing", 1_100_000, 14, "Online ads"),
    Account("6200", "Software Licences", "IT", 900_000, 5, "SaaS subscription"),
    Account("6210", "Hardware", "IT", 300_000, 3, "Hardware purchase"),
    Account("6220", "Cloud Hosting", "IT", 600_000, 4, "Cloud invoice"),
    Account("6230", "IT Services", "IT", 500_000, 4, "IT service invoice"),
    Account("6300", "Office Rent", "Rent", 1_400_000, 1, "Monthly rent"),
    Account("6310", "Utilities", "Rent", 350_000, 1, "Utilities"),
    Account("6320", "Facility Management", "Rent", 250_000, 1, "Facility services"),
    Account("6400", "Travel Expenses", "Travel", 600_000, 10, "Travel expense report"),
    Account("6410", "Accommodation", "Travel", 300_000, 6, "Hotel invoice"),
    Account("6420", "Entertainment", "Travel", 150_000, 4, "Client entertainment"),
    Account("6500", "Depreciation Equipment", "Depreciation", 1_600_000, 1, "Depreciation run"),
    Account("6510", "Amortisation Software", "Depreciation", 400_000, 1, "Amortisation run"),
    Account("6600", "Legal & Consulting", "Other OpEx", 600_000, 3, "Consulting invoice"),
    Account("6610", "Insurance", "Other OpEx", 350_000, 1, "Insurance premium"),
    Account("6620", "Bank Fees", "Other OpEx", 80_000, 3, "Bank charges"),
    Account("6630", "Office Supplies", "Other OpEx", 120_000, 5, "Office supplies"),
)

COST_CENTRES: tuple[dict[str, str], ...] = (
    {"code": "CC100", "name": "Sales DACH", "department": "Sales", "region": "DACH",
     "manager": "Anna Keller"},
    {"code": "CC110", "name": "Sales Benelux", "department": "Sales", "region": "Benelux",
     "manager": "Pieter de Vries"},
    {"code": "CC120", "name": "Sales Nordics", "department": "Sales", "region": "Nordics",
     "manager": "Ingrid Lindqvist"},
    {"code": "CC200", "name": "Operations DACH", "department": "Operations", "region": "DACH",
     "manager": "Markus Brandt"},
    {"code": "CC210", "name": "Operations Nordics", "department": "Operations",
     "region": "Nordics", "manager": "Erik Johansson"},
    {"code": "CC300", "name": "Marketing DACH", "department": "Marketing", "region": "DACH",
     "manager": "Julia Hoffmann"},
    {"code": "CC310", "name": "Marketing Benelux", "department": "Marketing",
     "region": "Benelux", "manager": "Sanne Jansen"},
    {"code": "CC400", "name": "Administration", "department": "Administration",
     "region": "DACH", "manager": "Thomas Wagner"},
)

_HEADCOUNT = {"CC100": .16, "CC110": .10, "CC120": .08, "CC200": .22, "CC210": .12,
              "CC300": .07, "CC310": .05, "CC400": .20}

# How each P&L group is distributed across cost centres (weights sum to 1).
GROUP_ALLOCATION: dict[str, dict[str, float]] = {
    "Revenue": {"CC100": .50, "CC110": .30, "CC120": .20},
    "Cost of Goods Sold": {"CC200": .65, "CC210": .35},
    "Personnel Costs": _HEADCOUNT,
    "Marketing": {"CC300": .60, "CC310": .40},
    "IT": {"CC100": .08, "CC110": .05, "CC120": .05, "CC200": .15, "CC210": .08,
           "CC300": .10, "CC310": .09, "CC400": .40},
    "Rent": _HEADCOUNT,
    "Travel": {"CC100": .25, "CC110": .20, "CC120": .20, "CC300": .10, "CC310": .10,
               "CC400": .15},
    "Depreciation": {"CC200": .50, "CC210": .30, "CC400": .20},
    "Other OpEx": {"CC100": .10, "CC200": .10, "CC300": .10, "CC400": .70},
}

# Monthly seasonality (Jan..Dec), normalised to a mean of 1 at runtime.
SEASONALITY: dict[str, list[float]] = {
    "Revenue": [0.85, 0.90, 1.05, 1.00, 1.00, 1.00, 0.90, 0.75, 1.05, 1.10, 1.15, 1.25],
    "Cost of Goods Sold": [0.85, 0.90, 1.05, 1.00, 1.00, 1.00, 0.90, 0.75, 1.05, 1.10, 1.15, 1.25],
    "Marketing": [0.70, 0.90, 1.20, 1.20, 1.00, 0.90, 0.60, 0.60, 1.20, 1.30, 1.20, 1.20],
    "Travel": [0.80, 1.00, 1.10, 1.10, 1.10, 1.00, 0.70, 0.60, 1.10, 1.20, 1.20, 1.10],
    "6020": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1],  # bonuses paid in March and December
}

# Budget growth index per fiscal year.
GROWTH: dict[str, dict[int, float]] = {
    "Revenue": {2023: 1.00, 2024: 1.08, 2025: 1.17},
    "Personnel Costs": {2023: 1.00, 2024: 1.06, 2025: 1.12},
    "default": {2023: 1.00, 2024: 1.05, 2025: 1.10},
}

# Noise (std. dev. of actual vs. budget) per P&L group.
NOISE: dict[str, float] = {
    "Revenue": 0.06, "Cost of Goods Sold": 0.06, "Personnel Costs": 0.02, "Rent": 0.005,
    "Depreciation": 0.0, "default": 0.10,
}

# Structural deviations (the "stories" behind the dashboard).
# (condition, bias) – conditions match on group / account / cost centre / year / months.
DEVIATIONS: tuple[dict[str, object], ...] = (
    # Marketing Benelux is consistently over budget – and it gets worse every year.
    {"cc": "CC310", "year": 2023, "bias": 0.14},
    {"cc": "CC310", "year": 2024, "bias": 0.18},
    {"cc": "CC310", "year": 2025, "bias": 0.22},
    # Revenue: slightly ahead in 2023, a miss in 2024, recovery in 2025 (Nordics strong).
    {"group": "Revenue", "year": 2023, "bias": 0.02},
    {"group": "Revenue", "year": 2024, "bias": -0.04},
    {"group": "Revenue", "year": 2025, "bias": 0.01},
    {"group": "Revenue", "cc": "CC120", "year": 2025, "bias": 0.08},
    # COGS: material price inflation in 2024 squeezes gross margin.
    {"group": "Cost of Goods Sold", "year": 2023, "bias": 0.02},
    {"group": "Cost of Goods Sold", "year": 2024, "bias": 0.01},
    {"account": "5000", "year": 2024, "bias": 0.05},
    {"group": "Cost of Goods Sold", "year": 2025, "bias": 0.01},
    # Specific cost overruns.
    {"account": "6220", "year": 2025, "bias": 0.30},  # cloud migration
    {"group": "Travel", "year": 2023, "bias": 0.15},  # post-pandemic catch-up
    {"account": "6600", "year": 2024, "months": (6, 7, 8, 9), "bias": 0.90},  # ERP project
    {"account": "6040", "year": 2025, "bias": 0.25},  # temporary staff in operations
)

ISSUE_COUNTS: dict[str, int] = {
    "duplicate_booking": 300,
    "missing_cost_centre": 200,
    "unknown_account": 200,
    "wrong_period": 150,
    "negative_revenue": 150,
}
UNKNOWN_ACCOUNT_CODES: tuple[str, ...] = ("4999", "6999", "9100")
TX_SCALE: float = 1.33  # scales posting volume to ~50k GL rows


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _season(key: str) -> np.ndarray:
    """Return a 12-month seasonality vector normalised to a mean of 1."""
    raw = np.asarray(SEASONALITY.get(key, [1.0] * 12), dtype=float)
    return raw / raw.mean()


def _bias(acc: Account, cc: str, year: int, month: int) -> float:
    """Sum all structural deviations that apply to one account/cost-centre/month."""
    total = 0.0
    for dev in DEVIATIONS:
        if "group" in dev and dev["group"] != acc.group:
            continue
        if "account" in dev and dev["account"] != acc.code:
            continue
        if "cc" in dev and dev["cc"] != cc:
            continue
        if dev["year"] != year:
            continue
        if "months" in dev and month not in dev["months"]:  # type: ignore[operator]
            continue
        total += float(dev["bias"])  # type: ignore[arg-type]
    return total


def _split_amount(rng: np.random.Generator, total: float, n: int) -> np.ndarray:
    """Split a monthly total into ``n`` positive postings that sum exactly to the total."""
    if n == 1:
        return np.array([round(total, 2)])
    weights = rng.gamma(shape=2.0, scale=1.0, size=n)
    parts = np.round(total * weights / weights.sum(), 2)
    parts[-1] = round(total - parts[:-1].sum(), 2)
    if parts[-1] <= 0:  # extremely unlikely; fall back to an even split
        parts = np.full(n, round(total / n, 2))
        parts[-1] = round(total - parts[:-1].sum(), 2)
    return parts


# --------------------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------------------


def build_master_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the chart of accounts and the cost-centre master as DataFrames."""
    coa = pd.DataFrame(
        {
            "account_code": [a.code for a in ACCOUNTS],
            "account_name": [a.name for a in ACCOUNTS],
            "pnl_group": [a.group for a in ACCOUNTS],
            "pnl_category": [PNL_GROUPS[a.group]["category"] for a in ACCOUNTS],
            "pnl_group_sort": [PNL_GROUPS[a.group]["sort"] for a in ACCOUNTS],
            "sign": [PNL_GROUPS[a.group]["sign"] for a in ACCOUNTS],
        }
    )
    ccs = pd.DataFrame(
        {
            "cost_centre_code": [c["code"] for c in COST_CENTRES],
            "cost_centre_name": [c["name"] for c in COST_CENTRES],
            "department": [c["department"] for c in COST_CENTRES],
            "region": [c["region"] for c in COST_CENTRES],
            "manager": [c["manager"] for c in COST_CENTRES],
        }
    )
    return coa, ccs


def build_plan_and_actual_totals(rng: np.random.Generator) -> pd.DataFrame:
    """Return monthly budget, forecast and actual totals per account and cost centre."""
    rows: list[dict[str, object]] = []
    for acc in ACCOUNTS:
        season = _season(acc.code if acc.code in SEASONALITY else acc.group)
        growth = GROWTH.get(acc.group, GROWTH["default"])
        sigma = NOISE.get(acc.group, NOISE["default"])
        for cc, weight in GROUP_ALLOCATION[acc.group].items():
            for year in FISCAL_YEARS:
                for month in range(1, 13):
                    budget = acc.annual_base * weight * growth[year] * season[month - 1] / 12
                    if budget <= 0:
                        continue
                    deviation = _bias(acc, cc, year, month) + rng.normal(0.0, sigma)
                    actual = budget * max(0.05, 1.0 + deviation)
                    # Rolling forecast: captures ~75% of the true deviation plus some error.
                    fc_dev = 0.75 * (actual / budget - 1.0) + rng.normal(0.0, 0.02)
                    forecast = budget * max(0.05, 1.0 + fc_dev)
                    rows.append(
                        {
                            "period": f"{year}-{month:02d}",
                            "account_code": acc.code,
                            "cost_centre_code": cc,
                            "budget": round(budget, 2),
                            "forecast": round(forecast, 2),
                            "actual": round(actual, 2),
                        }
                    )
    return pd.DataFrame(rows)


def build_gl(rng: np.random.Generator, totals: pd.DataFrame) -> pd.DataFrame:
    """Explode monthly actual totals into transaction-level GL postings."""
    acc_by_code = {a.code: a for a in ACCOUNTS}
    records: list[tuple[object, ...]] = []
    for row in totals.itertuples(index=False):
        acc = acc_by_code[row.account_code]
        year, month = int(row.period[:4]), int(row.period[5:])
        n = 1 if acc.tx_per_month <= 1 else max(1, int(rng.poisson(acc.tx_per_month * TX_SCALE)))
        amounts = _split_amount(rng, float(row.actual), n)
        if acc.group in ("Rent", "Depreciation") or acc.code in ("6010", "6020", "6610"):
            days = np.full(n, 1 if acc.group == "Rent" else 28)
        else:
            days = rng.integers(1, 29, size=n)
        for amount, day in zip(amounts, days, strict=True):
            records.append(
                (f"{year}-{month:02d}-{int(day):02d}", row.period, acc.code,
                 row.cost_centre_code, float(amount), acc.text)
            )
    gl = pd.DataFrame(
        records,
        columns=["posting_date", "period", "account_code", "cost_centre_code", "amount", "text"],
    )
    gl = gl.sort_values(["posting_date", "account_code", "cost_centre_code"], kind="mergesort")
    gl = gl.reset_index(drop=True)
    gl.insert(0, "entry_id", [f"JE{i:07d}" for i in range(1, len(gl) + 1)])
    gl.insert(1, "document_ref", [f"DOC-{i:08d}" for i in rng.permutation(len(gl)) + 10_000_000])
    gl.insert(6, "currency", CURRENCY)
    return gl


def _shift_period(period: str, months: int) -> str:
    """Shift a ``YYYY-MM`` period string by a number of months."""
    year, month = int(period[:4]), int(period[5:])
    idx = year * 12 + (month - 1) + months
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def inject_issues(
    rng: np.random.Generator, gl: pd.DataFrame, revenue_codes: set[str]
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Inject ~2% data-quality issues into the ledger and return a log of every change.

    Each affected row carries exactly one issue so that detection can be verified 1:1.
    """
    gl = gl.copy()
    issues: list[dict[str, object]] = []
    is_revenue = gl["account_code"].isin(revenue_codes).to_numpy()
    available = np.ones(len(gl), dtype=bool)

    def take(n: int, mask: np.ndarray) -> np.ndarray:
        candidates = np.flatnonzero(available & mask)
        chosen = np.sort(rng.choice(candidates, size=n, replace=False))
        available[chosen] = False
        return chosen

    everything = np.ones(len(gl), dtype=bool)

    for idx in take(ISSUE_COUNTS["negative_revenue"], is_revenue):
        gl.at[idx, "amount"] = -gl.at[idx, "amount"]
        issues.append({"issue_type": "negative_revenue", "entry_id": gl.at[idx, "entry_id"],
                       "detail": "Revenue amount booked with inverted sign"})

    for idx in take(ISSUE_COUNTS["missing_cost_centre"], everything):
        issues.append({"issue_type": "missing_cost_centre", "entry_id": gl.at[idx, "entry_id"],
                       "detail": f"Cost centre {gl.at[idx, 'cost_centre_code']} removed"})
        gl.at[idx, "cost_centre_code"] = None

    for idx in take(ISSUE_COUNTS["unknown_account"], everything):
        new_code = str(rng.choice(UNKNOWN_ACCOUNT_CODES))
        issues.append({"issue_type": "unknown_account", "entry_id": gl.at[idx, "entry_id"],
                       "detail": f"Account {gl.at[idx, 'account_code']} replaced by {new_code}"})
        gl.at[idx, "account_code"] = new_code

    for idx in take(ISSUE_COUNTS["wrong_period"], everything):
        original = gl.at[idx, "period"]
        shift = int(rng.choice([-3, -2, -1, 1, 2, 3, 36, -36]))
        gl.at[idx, "period"] = _shift_period(original, shift)
        issues.append({"issue_type": "wrong_period", "entry_id": gl.at[idx, "entry_id"],
                       "detail": f"Period {original} changed to {gl.at[idx, 'period']} "
                                 f"(posting date {gl.at[idx, 'posting_date']})"})

    # Duplicates: re-post clean rows under a new entry_id (same document_ref and amount).
    sources = take(ISSUE_COUNTS["duplicate_booking"], everything)
    dupes = gl.iloc[sources].copy()
    next_id = len(gl) + 1
    dupes["entry_id"] = [f"JE{i:07d}" for i in range(next_id, next_id + len(dupes))]
    for src, new_id in zip(gl.iloc[sources]["entry_id"], dupes["entry_id"], strict=True):
        issues.append({"issue_type": "duplicate_booking", "entry_id": new_id,
                       "detail": f"Duplicate of {src}"})
    gl = pd.concat([gl, dupes], ignore_index=True)
    gl = gl.sort_values(["posting_date", "entry_id"], kind="mergesort").reset_index(drop=True)
    issues.sort(key=lambda i: (str(i["issue_type"]), str(i["entry_id"])))
    return gl, issues


def generate(out_dir: Path = RAW_DIR, seed: int = SEED, sample_dir: Path | None = None) -> dict:
    """Generate all raw files into ``out_dir`` and return a small summary dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    coa, ccs = build_master_data()
    totals = build_plan_and_actual_totals(rng)
    gl_clean = build_gl(rng, totals)
    revenue_codes = set(coa.loc[coa["pnl_group"] == "Revenue", "account_code"])
    gl, issues = inject_issues(rng, gl_clean, revenue_codes)

    coa.to_csv(out_dir / "chart_of_accounts.csv", index=False)
    ccs.to_csv(out_dir / "cost_centres.csv", index=False)
    gl.to_csv(out_dir / "gl_actuals.csv", index=False, float_format="%.2f")
    plan_cols = ["period", "account_code", "cost_centre_code"]
    totals[[*plan_cols, "budget"]].rename(columns={"budget": "amount"}).to_csv(
        out_dir / "budget.csv", index=False, float_format="%.2f"
    )
    totals[[*plan_cols, "forecast"]].rename(columns={"forecast": "amount"}).to_csv(
        out_dir / "forecast.csv", index=False, float_format="%.2f"
    )

    summary = {
        "company": COMPANY,
        "seed": seed,
        "gl_rows": len(gl),
        "gl_rows_clean": len(gl) - len(issues),
        "issue_rate_pct": round(100 * len(issues) / len(gl), 2),
        "issue_counts": {k: sum(1 for i in issues if i["issue_type"] == k) for k in ISSUE_COUNTS},
    }
    with (out_dir / "_injected_issues.json").open("w", encoding="utf-8") as fh:
        json.dump({**summary, "issues": issues}, fh, indent=2)

    if sample_dir is not None:
        sample_dir.mkdir(parents=True, exist_ok=True)
        gl.head(500).to_csv(sample_dir / "gl_actuals_sample.csv", index=False, float_format="%.2f")
    return summary


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=RAW_DIR, help="output directory")
    parser.add_argument("--seed", type=int, default=SEED, help="random seed")
    args = parser.parse_args()
    summary = generate(args.out, args.seed, sample_dir=SAMPLE_DIR)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
