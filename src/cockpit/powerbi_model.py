"""Generate the Power BI Project (PBIP) with a TMDL semantic model.

Why generate instead of hand-writing? The table/column specification and the DAX measures
live in exactly one place (this module), and three artefacts are rendered from it:

* ``powerbi/ControllingCockpit.SemanticModel/definition/**.tmdl`` – the semantic model
* ``powerbi/ControllingCockpit.Report/**``                       – empty report pages (PBIR)
* ``powerbi/measures.dax``                                        – all measures, readable

A test (tests/test_powerbi_model.py) fails when the committed files drift from the spec.

Folder layout follows Microsoft Learn "Power BI Desktop project semantic model folder" and
"... report folder" (PBIR ``definition/`` folder, ``definition.pbism`` version >= 4.0 for
TMDL, ``definition.pbir`` with a relative ``byPath`` dataset reference).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from cockpit.config import ROOT

PBI_DIR: Path = ROOT / "powerbi"
PROJECT: str = "ControllingCockpit"
SM_DIR: Path = PBI_DIR / f"{PROJECT}.SemanticModel"
REPORT_DIR: Path = PBI_DIR / f"{PROJECT}.Report"
_NS = uuid.UUID("7b0c2a4e-8f1d-4c55-9a51-2b7f6c1e9d00")  # namespace for deterministic tags

DEFAULT_DATA_FOLDER = "C:\\Projects\\controlling-cockpit\\data\\model\\"

FMT_EUR = "€#,##0;-€#,##0;€0"
FMT_PCT = "0.0%;-0.0%;0.0%"
FMT_PCT_SIGNED = "+0.0%;-0.0%;0.0%"
FMT_INT = "#,##0"


# --------------------------------------------------------------------------------------
# Specification
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    """A model column loaded from a CSV column."""

    source: str
    name: str
    data_type: str  # int64 | string | double | decimal | dateTime | boolean
    hidden: bool = False
    sort_by: str | None = None
    format_string: str | None = None
    summarize_by: str = "none"
    is_key: bool = False
    description: str | None = None


@dataclass(frozen=True)
class Hierarchy:
    """A user hierarchy: list of (level name, column name)."""

    name: str
    levels: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TableSpec:
    """A model table backed by one CSV file in the data folder."""

    name: str
    file: str
    description: str
    columns: tuple[Column, ...]
    hierarchies: tuple[Hierarchy, ...] = ()
    is_date_table: bool = False
    hidden: bool = False


@dataclass(frozen=True)
class Measure:
    """A DAX measure in the _Measures table."""

    name: str
    expression: str
    format_string: str
    folder: str
    description: str


@dataclass(frozen=True)
class Relationship:
    """A single-direction, many-to-one relationship (from = many side)."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class ModelSpec:
    """The complete semantic model."""

    tables: list[TableSpec] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


def C(source: str, name: str, dtype: str, **kw: object) -> Column:  # noqa: N802
    """Shorthand constructor for :class:`Column`."""
    return Column(source, name, dtype, **kw)  # type: ignore[arg-type]


TABLES: list[TableSpec] = [
    TableSpec(
        "Date", "dim_date.csv",
        "Daily calendar 2023-01-01 to 2025-12-31. Fiscal year = calendar year. Marked as date "
        "table.",
        (
            C("date_key", "Date Key", "int64", hidden=True),
            C("date", "Date", "dateTime", is_key=True, format_string="yyyy-mm-dd"),
            C("fiscal_year", "Fiscal Year", "int64", format_string="0"),
            C("fiscal_year_label", "Fiscal Year Label", "string", sort_by="Fiscal Year"),
            C("fiscal_quarter", "Fiscal Quarter", "int64", hidden=True),
            C("fiscal_quarter_label", "Quarter", "string", sort_by="Fiscal Quarter"),
            C("year_quarter", "Year Quarter", "string"),
            C("month_number", "Month Number", "int64", hidden=True),
            C("month_name", "Month", "string", sort_by="Month Number"),
            C("month_short", "Month Short", "string", sort_by="Month Number"),
            C("period", "Period", "string", sort_by="Period Sort",
              description="Fiscal period YYYY-MM."),
            C("period_sort", "Period Sort", "int64", hidden=True),
            C("month_start", "Month Start", "dateTime", format_string="yyyy-mm-dd"),
            C("day_of_month", "Day of Month", "int64", hidden=True),
            C("weekday_name", "Weekday", "string", sort_by="Weekday Number", hidden=True),
            C("weekday_number", "Weekday Number", "int64", hidden=True),
            C("is_weekend", "Is Weekend", "boolean", hidden=True),
        ),
        hierarchies=(Hierarchy("Fiscal Calendar", (("Year", "Fiscal Year Label"),
                                                   ("Quarter", "Quarter"),
                                                   ("Month", "Month Short"))),),
        is_date_table=True,
    ),
    TableSpec(
        "Account", "dim_account.csv",
        "Chart of accounts with P&L hierarchy (category > group > account) and P&L sign.",
        (
            C("account_key", "Account Key", "int64", hidden=True),
            C("account_code", "Account Code", "string"),
            C("account_name", "Account Name", "string"),
            C("account_label", "Account", "string", sort_by="Account Code"),
            C("pnl_group", "P&L Group", "string", sort_by="P&L Group Sort"),
            C("pnl_group_sort", "P&L Group Sort", "int64", hidden=True),
            C("pnl_category", "P&L Category", "string", sort_by="P&L Category Sort"),
            C("pnl_category_sort", "P&L Category Sort", "int64", hidden=True),
            C("sign", "Sign", "int64",
              description="+1 for income, -1 for expense. Multiply natural amounts by this "
                          "sign to get P&L impact."),
            C("account_type", "Account Type", "string"),
        ),
        hierarchies=(Hierarchy("P&L Hierarchy", (("Category", "P&L Category"),
                                                 ("Group", "P&L Group"),
                                                 ("Account", "Account"))),),
    ),
    TableSpec(
        "Cost Centre", "dim_cost_centre.csv",
        "Cost centres with department, region and responsible manager.",
        (
            C("cost_centre_key", "Cost Centre Key", "int64", hidden=True),
            C("cost_centre_code", "Cost Centre Code", "string"),
            C("cost_centre_name", "Cost Centre Name", "string"),
            C("cost_centre_label", "Cost Centre", "string", sort_by="Cost Centre Code"),
            C("department", "Department", "string"),
            C("region", "Region", "string"),
            C("manager", "Manager", "string"),
        ),
        hierarchies=(Hierarchy("Organisation", (("Department", "Department"),
                                                ("Cost Centre", "Cost Centre"))),),
    ),
    TableSpec(
        "Scenario", "dim_scenario.csv",
        "Planning scenario: Actual, Budget, Forecast.",
        (
            C("scenario_key", "Scenario Key", "int64", hidden=True),
            C("scenario", "Scenario", "string", sort_by="Scenario Sort"),
            C("scenario_sort", "Scenario Sort", "int64", hidden=True),
            C("description", "Scenario Description", "string"),
        ),
    ),
    TableSpec(
        "Fact Finance", "fact_finance.csv",
        "Monthly amounts per account, cost centre and scenario. Natural sign (revenue and "
        "costs positive). Use the measures in _Measures instead of the raw columns.",
        (
            C("date_key", "Date Key", "int64", hidden=True),
            C("account_key", "Account Key", "int64", hidden=True),
            C("cost_centre_key", "Cost Centre Key", "int64", hidden=True),
            C("scenario_key", "Scenario Key", "int64", hidden=True),
            C("amount", "Amount", "decimal", hidden=True, summarize_by="sum",
              format_string=FMT_EUR),
            C("line_count", "Line Count", "int64", hidden=True, summarize_by="sum",
              description="Number of GL postings aggregated into this row (1 for plan data)."),
        ),
    ),
    TableSpec(
        "Rejected Rows", "fact_finance_rejected.csv",
        "Quarantined source records that failed an ERROR-severity data-quality check.",
        (
            C("scenario", "Scenario", "string"),
            C("source_table", "Source Table", "string"),
            C("record_key", "Record Key", "string"),
            C("document_ref", "Document Ref", "string"),
            C("posting_date", "Posting Date", "dateTime", format_string="yyyy-mm-dd"),
            C("period", "Period", "string"),
            C("account_code", "Account Code", "string"),
            C("cost_centre_code", "Cost Centre Code", "string"),
            C("amount", "Amount", "decimal", format_string=FMT_EUR, summarize_by="sum"),
            C("reject_check_id", "Check ID", "string"),
            C("reject_reason", "Reject Reason", "string"),
            C("all_check_ids", "All Check IDs", "string"),
            C("rejected_at", "Rejected At", "dateTime", format_string="yyyy-mm-dd hh:nn"),
        ),
    ),
    TableSpec(
        "DQ Results", "dq_results.csv",
        "One row per data-quality check with severity, status and affected rows.",
        (
            C("check_id", "Check ID", "string"),
            C("check_name", "Check Name", "string"),
            C("check_category", "Check Category", "string"),
            C("source_table", "Source Table", "string"),
            C("severity", "Severity", "string"),
            C("rows_checked", "Rows Checked", "int64", summarize_by="sum", format_string=FMT_INT),
            C("rows_affected", "Rows Affected", "int64", summarize_by="sum",
              format_string=FMT_INT),
            C("pct_affected", "Pct Affected", "double", format_string="0.000"),
            C("amount_affected", "Amount Affected", "decimal", summarize_by="sum",
              format_string=FMT_EUR),
            C("status", "Status", "string"),
            C("sample_keys", "Sample Keys", "string"),
            C("description", "Check Description", "string"),
            C("checked_at", "Checked At", "dateTime", format_string="yyyy-mm-dd hh:nn"),
        ),
    ),
]

RELATIONSHIPS: list[Relationship] = [
    Relationship("Fact Finance", "Date Key", "Date", "Date Key"),
    Relationship("Fact Finance", "Account Key", "Account", "Account Key"),
    Relationship("Fact Finance", "Cost Centre Key", "Cost Centre", "Cost Centre Key"),
    Relationship("Fact Finance", "Scenario Key", "Scenario", "Scenario Key"),
    Relationship("Rejected Rows", "Check ID", "DQ Results", "Check ID"),
]


def _m(name: str) -> str:
    return f"[{name}]"


MEASURES: list[Measure] = [
    # --- Base -------------------------------------------------------------------------
    Measure("Actual",
            'CALCULATE ( SUM ( \'Fact Finance\'[Amount] ), \'Scenario\'[Scenario] = "Actual" )',
            FMT_EUR, "1 Base",
            "Booked actuals after data-quality checks, natural sign (revenue and costs "
            "positive)."),
    Measure("Budget",
            'CALCULATE ( SUM ( \'Fact Finance\'[Amount] ), \'Scenario\'[Scenario] = "Budget" )',
            FMT_EUR, "1 Base", "Approved budget, natural sign."),
    Measure("Forecast",
            'CALCULATE ( SUM ( \'Fact Finance\'[Amount] ), \'Scenario\'[Scenario] = "Forecast" )',
            FMT_EUR, "1 Base", "Latest rolling forecast, natural sign."),
    Measure("Actual (P&L)",
            "CALCULATE (\n    SUMX ( 'Fact Finance', 'Fact Finance'[Amount] * RELATED ( "
            "'Account'[Sign] ) ),\n    'Scenario'[Scenario] = \"Actual\"\n)",
            FMT_EUR, "1 Base",
            "Actual with P&L sign (revenue +, costs -). Summed over all accounts = EBIT."),
    Measure("Budget (P&L)",
            "CALCULATE (\n    SUMX ( 'Fact Finance', 'Fact Finance'[Amount] * RELATED ( "
            "'Account'[Sign] ) ),\n    'Scenario'[Scenario] = \"Budget\"\n)",
            FMT_EUR, "1 Base", "Budget with P&L sign (revenue +, costs -)."),
    # --- Variance ---------------------------------------------------------------------
    Measure("Variance (Abs)", "[Actual] - [Budget]", FMT_EUR, "2 Variance",
            "Actual minus Budget in natural sign. For cost lines a positive value means over "
            "budget (adverse); for revenue it means ahead of budget (favourable)."),
    Measure("Variance %", "DIVIDE ( [Variance (Abs)], ABS ( [Budget] ) )", FMT_PCT_SIGNED,
            "2 Variance", "Variance (Abs) divided by Budget."),
    Measure("Variance (P&L Impact)", "[Actual (P&L)] - [Budget (P&L)]", FMT_EUR, "2 Variance",
            "Sign-aware variance: positive = favourable for profit, negative = adverse. Use "
            "this for red/green conditional formatting across revenue and cost lines."),
    Measure("Variance % (P&L Impact)",
            "DIVIDE ( [Variance (P&L Impact)], ABS ( [Budget (P&L)] ) )", FMT_PCT_SIGNED,
            "2 Variance", "Sign-aware variance in percent of budget."),
    Measure("Variance Colour",
            "VAR v = [Variance % (P&L Impact)]\nRETURN\n    SWITCH (\n        TRUE (),\n"
            "        ISBLANK ( v ), BLANK (),\n        v >= 0, \"#2E7D32\",\n"
            "        v >= -0.05, \"#F9A825\",\n        \"#C62828\"\n    )",
            "", "2 Variance",
            "Hex colour for conditional formatting (field value): green = favourable, amber = "
            "up to 5% adverse, red = more than 5% adverse."),
    # --- Time intelligence --------------------------------------------------------------
    Measure("Actual YTD", "CALCULATE ( [Actual], DATESYTD ( 'Date'[Date] ) )", FMT_EUR,
            "3 Time Intelligence", "Actual year-to-date within the fiscal year."),
    Measure("Budget YTD", "CALCULATE ( [Budget], DATESYTD ( 'Date'[Date] ) )", FMT_EUR,
            "3 Time Intelligence", "Budget year-to-date within the fiscal year."),
    Measure("Budget (Full Year)",
            "CALCULATE ( [Budget], REMOVEFILTERS ( 'Date' ), VALUES ( 'Date'[Fiscal Year] ) )",
            FMT_EUR, "3 Time Intelligence",
            "Full-year budget of the fiscal year(s) in context, ignoring month filters."),
    Measure("Actual PY", "CALCULATE ( [Actual], SAMEPERIODLASTYEAR ( 'Date'[Date] ) )",
            FMT_EUR, "3 Time Intelligence", "Actual of the same period in the prior year."),
    Measure("YoY %", "DIVIDE ( [Actual] - [Actual PY], ABS ( [Actual PY] ) )", FMT_PCT_SIGNED,
            "3 Time Intelligence",
            "Year-over-year growth of Actual. Blank for FY2023 (no prior year loaded)."),
    Measure("Budget Consumption %", "DIVIDE ( [Actual YTD], [Budget (Full Year)] )", FMT_PCT,
            "3 Time Intelligence",
            "Share of the full-year budget already consumed year-to-date. Mainly meaningful "
            "for cost centres."),
    # --- P&L KPIs -----------------------------------------------------------------------
    Measure("Revenue", "CALCULATE ( [Actual], 'Account'[P&L Category] = \"Revenue\" )",
            FMT_EUR, "4 P&L KPIs", "Actual revenue."),
    Measure("Revenue (Budget)",
            "CALCULATE ( [Budget], 'Account'[P&L Category] = \"Revenue\" )", FMT_EUR,
            "4 P&L KPIs", "Budgeted revenue."),
    Measure("COGS", "CALCULATE ( [Actual], 'Account'[P&L Category] = \"Cost of Goods Sold\" )",
            FMT_EUR, "4 P&L KPIs", "Actual cost of goods sold."),
    Measure("Gross Profit", "[Revenue] - [COGS]", FMT_EUR, "4 P&L KPIs",
            "Revenue minus cost of goods sold (actual)."),
    Measure("Gross Margin %", "DIVIDE ( [Gross Profit], [Revenue] )", FMT_PCT, "4 P&L KPIs",
            "Gross profit in percent of revenue (actual)."),
    Measure("Gross Margin % (Budget)",
            "VAR rev = CALCULATE ( [Budget], 'Account'[P&L Category] = \"Revenue\" )\n"
            "VAR cogs = CALCULATE ( [Budget], 'Account'[P&L Category] = \"Cost of Goods Sold\" )\n"
            "RETURN DIVIDE ( rev - cogs, rev )",
            FMT_PCT, "4 P&L KPIs", "Budgeted gross margin in percent of budgeted revenue."),
    Measure("Operating Expenses",
            "CALCULATE ( [Actual], 'Account'[P&L Category] = \"Operating Expenses\" )",
            FMT_EUR, "4 P&L KPIs", "Actual operating expenses (personnel, marketing, IT, ...)."),
    Measure("EBIT", "[Gross Profit] - [Operating Expenses]", FMT_EUR, "4 P&L KPIs",
            "Earnings before interest and taxes (actual): revenue - COGS - OpEx."),
    Measure("EBIT (Budget)", "[Budget (P&L)]", FMT_EUR, "4 P&L KPIs",
            "Budgeted EBIT: signed budget (revenue +, costs -) over the accounts in context."),
    Measure("EBIT YTD", "CALCULATE ( [EBIT], DATESYTD ( 'Date'[Date] ) )", FMT_EUR,
            "4 P&L KPIs", "EBIT year-to-date (actual)."),
    Measure("EBIT (Budget) YTD", "CALCULATE ( [EBIT (Budget)], DATESYTD ( 'Date'[Date] ) )",
            FMT_EUR, "4 P&L KPIs", "EBIT year-to-date (budget)."),
    Measure("Operating Margin (EBIT) %", "DIVIDE ( [EBIT], [Revenue] )", FMT_PCT, "4 P&L KPIs",
            "EBIT in percent of revenue (actual)."),
    Measure("Operating Margin (EBIT) % (Budget)",
            "DIVIDE ( [EBIT (Budget)], [Revenue (Budget)] )", FMT_PCT, "4 P&L KPIs",
            "Budgeted EBIT in percent of budgeted revenue."),
    # --- Forecast ----------------------------------------------------------------------
    Measure("Forecast Accuracy %",
            "VAR grain =\n    SUMMARIZE (\n        'Fact Finance',\n        'Date'[Period],\n"
            "        'Account'[Account Code],\n        'Cost Centre'[Cost Centre Code]\n    )\n"
            "VAR absError = SUMX ( grain, ABS ( [Actual] - [Forecast] ) )\n"
            "VAR absActual = SUMX ( grain, ABS ( [Actual] ) )\n"
            "RETURN IF ( absActual > 0, 1 - DIVIDE ( absError, absActual ) )",
            FMT_PCT, "5 Forecast",
            "1 - WAPE: 1 - sum|Actual - Forecast| / sum|Actual| at month x account x cost-centre "
            "grain, so over- and under-forecasts cannot cancel out."),
    Measure("Forecast vs Actual (Abs)", "[Forecast] - [Actual]", FMT_EUR, "5 Forecast",
            "Forecast minus Actual (natural sign)."),
    # --- Data quality ------------------------------------------------------------------
    Measure("Rejected Rows", "COUNTROWS ( 'Rejected Rows' )", FMT_INT, "6 Data Quality",
            "Number of quarantined source records."),
    Measure("Rejected Amount", "SUM ( 'Rejected Rows'[Amount] )", FMT_EUR, "6 Data Quality",
            "Total amount of quarantined source records (natural sign)."),
    Measure("DQ Checks Failed",
            "CALCULATE ( COUNTROWS ( 'DQ Results' ), 'DQ Results'[Status] = \"FAIL\" )",
            FMT_INT, "6 Data Quality", "Number of checks with status FAIL."),
    Measure("DQ Checks Passed %",
            "DIVIDE (\n    CALCULATE ( COUNTROWS ( 'DQ Results' ), 'DQ Results'[Status] = "
            "\"PASS\" ),\n    COUNTROWS ( 'DQ Results' )\n)",
            FMT_PCT, "6 Data Quality", "Share of checks that passed."),
    Measure("Clean Row Rate %",
            "VAR ledgerRows =\n    CALCULATE (\n        MAX ( 'DQ Results'[Rows Checked] ),\n"
            "        REMOVEFILTERS ( 'DQ Results' ),\n"
            "        'DQ Results'[Source Table] = \"stg_gl_actuals\"\n    )\n"
            "VAR rejected =\n    CALCULATE ( COUNTROWS ( 'Rejected Rows' ), "
            "'Rejected Rows'[Scenario] = \"Actual\" )\n"
            "RETURN DIVIDE ( ledgerRows - rejected, ledgerRows )",
            FMT_PCT, "6 Data Quality",
            "Share of general-ledger rows that passed all ERROR checks and were loaded."),
    Measure("DQ Status Colour",
            "SWITCH (\n    SELECTEDVALUE ( 'DQ Results'[Status] ),\n    \"PASS\", \"#2E7D32\",\n"
            "    \"WARN\", \"#F9A825\",\n    \"FAIL\", \"#C62828\"\n)",
            "", "6 Data Quality",
            "Hex colour per check status for conditional formatting (field value)."),
    # --- Labels ------------------------------------------------------------------------
    Measure("Report Title",
            "VAR yr =\n    IF (\n        HASONEVALUE ( 'Date'[Fiscal Year Label] ),\n"
            "        VALUES ( 'Date'[Fiscal Year Label] ),\n        \"FY2023–FY2025\"\n    )\n"
            "VAR dept =\n    IF (\n        ISFILTERED ( 'Cost Centre'[Department] ),\n"
            "        CONCATENATEX ( VALUES ( 'Cost Centre'[Department] ), "
            "'Cost Centre'[Department], \", \" ),\n        \"All departments\"\n    )\n"
            "RETURN \"Nordwerk GmbH · Budget vs. Actual · \" & yr & \" · \" & dept",
            "", "7 Labels",
            "Dynamic page title reflecting the selected fiscal year and departments."),
    Measure("Variance Commentary",
            "VAR v = [Variance (P&L Impact)]\nRETURN\n    IF (\n        NOT ISBLANK ( v ),\n"
            "        IF ( v >= 0, \"Favourable by \", \"Adverse by \" )\n"
            "            & FORMAT ( ABS ( v ), \"€#,##0\" )\n"
            "            & \" (\" & FORMAT ( [Variance % (P&L Impact)], \"+0.0%;-0.0%\" ) & \")\"\n"
            "    )",
            "", "7 Labels", "One-line text for KPI card subtitles and tooltips."),
]


# --------------------------------------------------------------------------------------
# Rendering helpers
# --------------------------------------------------------------------------------------


def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    if any(ch in name for ch in " .=:'&-()%") or not name[0].isalpha() and name[0] != "_":
        return "'" + name.replace("'", "''") + "'"
    return name


def tag(*parts: str) -> str:
    """Deterministic lineage tag so regenerated files are byte-identical."""
    return str(uuid.uuid5(_NS, "/".join(parts)))


_M_TYPES = {"int64": "Int64.Type", "string": "type text", "double": "type number",
            "decimal": "Currency.Type", "dateTime": "type datetime", "boolean": "type logical"}


def m_query(table: TableSpec) -> list[str]:
    """Power Query (M) that loads one CSV from the DataFolder parameter."""
    types = ",\n".join(f'\t{{"{c.source}", {_M_TYPES[c.data_type]}}}' for c in table.columns)
    renames = ",\n".join(f'\t{{"{c.source}", "{c.name}"}}' for c in table.columns)
    lines = [
        "let",
        f'\tSource = Csv.Document(File.Contents(DataFolder & "{table.file}"), '
        '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "\tPromoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        "\t// empty CSV fields -> null, so typed conversion does not raise errors",
        "\tNulls = Table.TransformColumns(Promoted, List.Transform(Table.ColumnNames(Promoted), "
        'each {_, (v) => if v = "" then null else v})),',
        "\t// en-US culture: decimal point is '.', independent of the Windows locale",
        "\tTyped = Table.TransformColumnTypes(Nulls, {",
        *[f"\t{line}" for line in types.split("\n")],
        '\t}, "en-US"),',
        "\tRenamed = Table.RenameColumns(Typed, {",
        *[f"\t{line}" for line in renames.split("\n")],
        "\t})",
        "in",
        "\tRenamed",
    ]
    return lines


def _desc(text: str, indent: str) -> list[str]:
    return [f"{indent}/// {line}" for line in text.split("\n")]


def render_table(table: TableSpec) -> str:
    """Render one table to TMDL."""
    out = [*_desc(table.description, ""), f"table {q(table.name)}"]
    out.append(f"\tlineageTag: {tag('table', table.name)}")
    if table.is_date_table:
        out.append("\tdataCategory: Time")
    out.append("")
    for col in table.columns:
        if col.description:
            out += _desc(col.description, "\t")
        out.append(f"\tcolumn {q(col.name)}")
        out.append(f"\t\tdataType: {col.data_type}")
        if col.is_key:
            out.append("\t\tisKey")
        if col.hidden:
            out.append("\t\tisHidden")
        if col.format_string:
            out.append(f"\t\tformatString: {col.format_string}")
        out.append(f"\t\tlineageTag: {tag('column', table.name, col.name)}")
        out.append(f"\t\tsummarizeBy: {col.summarize_by}")
        out.append(f"\t\tsourceColumn: {col.name}")
        if col.sort_by:
            out.append(f"\t\tsortByColumn: {q(col.sort_by)}")
        out.append("")
        if col.data_type == "dateTime":
            out.append("\t\tannotation UnderlyingDateTimeDataType = Date")
            out.append("")
    for h in table.hierarchies:
        out.append(f"\thierarchy {q(h.name)}")
        out.append(f"\t\tlineageTag: {tag('hierarchy', table.name, h.name)}")
        out.append("")
        for level, column in h.levels:
            out.append(f"\t\tlevel {q(level)}")
            out.append(f"\t\t\tlineageTag: {tag('level', table.name, h.name, level)}")
            out.append(f"\t\t\tcolumn: {q(column)}")
            out.append("")
    out.append(f"\tpartition {q(table.name)} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    out += [f"\t\t\t\t{line}" for line in m_query(table)]
    out.append("")
    out.append("\tannotation PBI_ResultType = Table")
    return "\n".join(out) + "\n"


def render_measures_table(measures: list[Measure]) -> str:
    """Render the _Measures table (measures only, one hidden placeholder column)."""
    out = [
        "/// Home table for all DAX measures. Contains no data (one hidden placeholder column).",
        "table _Measures",
        f"\tlineageTag: {tag('table', '_Measures')}",
        "",
    ]
    for m in measures:
        out += _desc(m.description, "\t")
        expr_lines = m.expression.split("\n")
        if len(expr_lines) == 1:
            out.append(f"\tmeasure {q(m.name)} = {expr_lines[0]}")
        else:
            out.append(f"\tmeasure {q(m.name)} =")
            out += [f"\t\t\t{line}" for line in expr_lines]
        if m.format_string:
            out.append(f"\t\tformatString: {m.format_string}")
        out.append(f"\t\tdisplayFolder: {m.folder}")
        out.append(f"\t\tlineageTag: {tag('measure', m.name)}")
        out.append("")
    out += [
        "\tcolumn Placeholder",
        "\t\tdataType: string",
        "\t\tisHidden",
        f"\t\tlineageTag: {tag('column', '_Measures', 'Placeholder')}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Placeholder",
        "",
        "\tpartition _Measures = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        "\t\t\t\t\tSource = #table(type table [Placeholder = text], {})",
        "\t\t\t\tin",
        "\t\t\t\t\tSource",
        "",
        "\tannotation PBI_ResultType = Table",
    ]
    return "\n".join(out) + "\n"


def render_relationships(rels: list[Relationship]) -> str:
    """Render relationships.tmdl (single direction, many-to-one = TMDL defaults)."""
    out: list[str] = []
    for r in rels:
        out.append(f"relationship {tag('rel', r.from_table, r.from_column)}")
        out.append(f"\tfromColumn: {q(r.from_table)}.{q(r.from_column)}")
        out.append(f"\ttoColumn: {q(r.to_table)}.{q(r.to_column)}")
        out.append("")
    return "\n".join(out)


def render_model(tables: list[str]) -> str:
    """Render model.tmdl."""
    order = json.dumps(["DataFolder", *tables])
    out = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        f"annotation PBI_QueryOrder = {order}",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        *[f"ref table {q(t)}" for t in tables],
        "",
    ]
    return "\n".join(out)


def render_expressions() -> str:
    """Render expressions.tmdl with the DataFolder parameter."""
    return (
        "/// Folder containing the exported star-schema CSV files (data/model/).\n"
        "/// Must end with a path separator. Change it in Power BI Desktop via\n"
        "/// Transform data > Edit parameters.\n"
        f'expression DataFolder = "{DEFAULT_DATA_FOLDER}" meta [IsParameterQuery=true, '
        'Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag('expression', 'DataFolder')}\n"
        "\n"
        "\tannotation PBI_ResultType = Text\n"
    )


def render_measures_dax(measures: list[Measure]) -> str:
    """Render all measures as a readable .dax file (same definitions as the TMDL)."""
    out = [
        "// =====================================================================",
        "// Controlling Cockpit – DAX measures (table: _Measures)",
        "// Generated from src/cockpit/powerbi_model.py – do not edit by hand.",
        "// Paste into DAX query view as DEFINE MEASURE statements, or read as reference.",
        "// =====================================================================",
        "",
    ]
    folder = None
    for m in measures:
        if m.folder != folder:
            folder = m.folder
            out += [f"// ---- {folder} " + "-" * (60 - len(folder)), ""]
        out.append(f"// {m.description}")
        if m.format_string:
            out.append(f"// Format: {m.format_string}")
        out.append(f"'_Measures'[{m.name}] =")
        out += [f"    {line}" for line in m.expression.split("\n")]
        out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# Report scaffold (PBIR) and project files
# --------------------------------------------------------------------------------------

_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
PAGES = [("ExecutiveOverview", "Executive Overview"),
         ("CostCentreDeepDive", "Cost Centre Deep-Dive"),
         ("DataQuality", "Data Quality")]


def render_files() -> dict[Path, str]:
    """Return every generated file (path -> content)."""
    files: dict[Path, str] = {}
    table_names = [t.name for t in TABLES] + ["_Measures"]
    d = SM_DIR / "definition"
    files[d / "database.tmdl"] = "database\n\tcompatibilityLevel: 1567\n"
    files[d / "model.tmdl"] = render_model(table_names)
    files[d / "expressions.tmdl"] = render_expressions()
    files[d / "relationships.tmdl"] = render_relationships(RELATIONSHIPS)
    for t in TABLES:
        files[d / "tables" / f"{t.name}.tmdl"] = render_table(t)
    files[d / "tables" / "_Measures.tmdl"] = render_measures_table(MEASURES)

    def js(obj: object) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"

    files[SM_DIR / "definition.pbism"] = js({
        "$schema": f"{_SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "settings": {},
    })
    files[REPORT_DIR / "definition.pbir"] = js({
        "$schema": f"{_SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{PROJECT}.SemanticModel"}},
    })
    rd = REPORT_DIR / "definition"
    files[rd / "version.json"] = js({
        "$schema": f"{_SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    files[rd / "report.json"] = js({
        "$schema": f"{_SCHEMA}/item/report/definition/report/1.0.0/schema.json",
        "themeCollection": {},
        "layoutOptimization": "None",
    })
    files[rd / "pages" / "pages.json"] = js({
        "$schema": f"{_SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p for p, _ in PAGES],
        "activePageName": PAGES[0][0],
    })
    for name, display in PAGES:
        files[rd / "pages" / name / "page.json"] = js({
            "$schema": f"{_SCHEMA}/item/report/definition/page/1.0.0/schema.json",
            "name": name,
            "displayName": display,
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        })
    files[PBI_DIR / f"{PROJECT}.pbip"] = js({
        "$schema": f"{_SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    files[PBI_DIR / "measures.dax"] = render_measures_dax(MEASURES)
    return files


def write_all() -> list[Path]:
    """Write all generated files to disk and return their paths."""
    written = []
    for path, content in render_files().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main() -> None:
    """CLI entry point."""
    paths = write_all()
    print(f"Power BI project written: {len(paths)} files under {PBI_DIR.relative_to(ROOT)}/")
    print(f"  {len(TABLES) + 1} tables, {len(MEASURES)} measures, "
          f"{len(RELATIONSHIPS)} relationships")


if __name__ == "__main__":
    main()
