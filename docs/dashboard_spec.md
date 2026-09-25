# Dashboard specification – Controlling Cockpit (Power BI)

This is the build sheet for the three report pages you create by hand in Power BI Desktop.
The semantic model (tables, relationships, 39 measures) already exists in
`powerbi/ControllingCockpit.SemanticModel`. The three pages exist as empty PBIR pages, so you
only add visuals.

> **Before you start:** open `powerbi/ControllingCockpit.pbip`, go to **Transform data → Edit
> parameters**, set `DataFolder` to the full path of `data/model\` (keep the trailing
> backslash), then **Close & Apply**.

---

## Global design rules

| Item | Setting |
|---|---|
| Canvas | 1280 × 720 (16:9), page view "Fit to page" (already set) |
| Theme | View → Themes → *Executive* (or *Default*), then customise the colours below |
| Colours | Navy `#1F3864` (actual / titles), Grey `#A6A6A6` (budget), Teal `#2E75B6` (forecast), Green `#2E7D32` (favourable), Amber `#F9A825` (≤ 5 % adverse), Red `#C62828` (> 5 % adverse) |
| Font | Segoe UI; titles 14 pt bold navy; card values 24 pt; axis labels 9 pt |
| Numbers | Display units **Thousands (K)** on charts; **Millions (M), 1 decimal** on KPI cards; tables show full € with no decimals |
| Grid | 16 px outer margin, 8 px gutter; left column 240 px for slicers on pages 1–2 |
| Sign logic | Use `Variance (P&L Impact)` / `Variance % (P&L Impact)` for any red/green colouring: positive = good for profit (works for both revenue and cost lines). `Variance (Abs)` is the plain Actual − Budget |
| Accessibility | Never use colour alone: every coloured variance also shows its sign (+/−). Add alt text to every visual |

**Reusable conditional formatting.** For font or background colour → *Format style: Field
value* → *Based on field:* `_Measures[Variance Colour]` (or `[DQ Status Colour]` on page 3).

---

## Page 1 – Executive Overview

**Question it answers:** *"Are we on budget this year, and what drives the gap?"*

| # | Visual type | Position (x, y, w, h) | Fields | Formatting |
|---|---|---|---|---|
| 1 | **Text box** with dynamic value | 16, 12, 1248, 40 | Text box → *+ Value* → `[Report Title]` | 18 pt bold navy, left aligned |
| 2 | **Slicer** (tile) | 16, 64, 240, 56 | `Date[Fiscal Year Label]` | Single select ON, default **FY2025**, no header |
| 3 | **Slicer** (dropdown) | 16, 128, 240, 56 | `Cost Centre[Department]` | Multi-select, "Select all" ON |
| 4 | **Slicer** (dropdown) | 16, 192, 240, 56 | `Cost Centre[Region]` | Multi-select |
| 5–9 | **Card (new)**, 5 cards in one visual | 272, 64, 992, 120 | Revenue · EBIT · Gross Margin % · Operating Margin (EBIT) % · Forecast Accuracy % | Callout value in M (1 dp) or %. **Reference label 1:** budget measure (`Revenue (Budget)`, `EBIT (Budget)`, `Gross Margin % (Budget)`, `Operating Margin (EBIT) % (Budget)`), title "Budget". **Reference label 2:** `Variance Commentary` coloured by `Variance Colour` |
| 10 | **Line and clustered column chart** | 272, 196, 600, 250 | X: `Date[Fiscal Calendar]` drilled to *Month*; Column y: `Revenue`; Line y: `Revenue (Budget)` | Columns navy, line grey dashed 2 px, markers ON. Title "Revenue – actual vs. budget by month" |
| 11 | **Line chart** | 884, 196, 380, 250 | X: `Date[Month Short]`; Y: `EBIT YTD`, `EBIT (Budget) YTD` | Actual navy solid, budget grey dashed. Title "EBIT year-to-date vs. budget" |
| 12 | **Waterfall chart** | 272, 458, 600, 250 | Category: `Account[P&L Group]`; Y: `Variance (P&L Impact)` | Sentiment colours: Increase green, Decrease red, Total grey. Sort by P&L Group (uses the hidden sort column). Data labels ON (K). Title "EBIT variance vs. budget by P&L group" |
| 13 | **Table** | 884, 458, 380, 250 | `Account[Account]`, `Cost Centre[Cost Centre]`, `Variance (Abs)`, `Variance %` | Visual-level filter: *Top N* → **Bottom 5** by `Variance (P&L Impact)` (= the 5 most adverse lines). `Variance %` font colour by field value `Variance Colour`. Title "Top 5 adverse variances" |

**Interactions:** the waterfall cross-filters the Top 5 table (Format → Edit interactions).
**Tooltip:** on visual 10 add `Variance %` and `Actual PY` to the tooltip well.

**How to read the waterfall.** Each bar shows how much a P&L group moved EBIT away from
budget. Revenue below budget and cost overruns show as red bars; the grey total bar equals
`EBIT − EBIT (Budget)`.

---

## Page 2 – Cost Centre Deep-Dive

**Question it answers:** *"Which cost centre is over budget, on which accounts, and is it
getting worse?"*

Page-level filter: `Account[Account Type]` = **Expense** (this page is about costs).

| # | Visual type | Position (x, y, w, h) | Fields | Formatting |
|---|---|---|---|---|
| 1 | **Text box** with dynamic value | 16, 12, 1248, 40 | `[Report Title]` | as page 1 |
| 2 | **Slicer** (tile) | 16, 64, 240, 56 | `Date[Fiscal Year Label]` | Single select, sync with page 1 (View → Sync slicers) |
| 3 | **Slicer** (list) | 16, 128, 240, 120 | `Cost Centre[Region]` | |
| 4 | **Gauge** | 16, 260, 240, 170 | Value: `Actual YTD`; Target: `Budget (Full Year)`; Max: leave auto | Fill navy, target line red. Title "Budget consumption" |
| 5 | **Card (new)** | 16, 440, 240, 80 | `Budget Consumption %` | Colour red when > 100 % (conditional formatting rules) |
| 6 | **Matrix** | 272, 64, 992, 360 | Rows: `Cost Centre[Organisation]` hierarchy (Department → Cost Centre), then `Account[P&L Group]`, then `Account[Account]`; Values: `Actual`, `Budget`, `Variance (Abs)`, `Variance %`, `Forecast`, `Actual PY`, `YoY %`, `Budget Consumption %` | Stepped layout ON; +/- icons ON; expand to *Cost Centre* level by default. **Conditional formatting:** `Variance %` → font colour by field value `Variance Colour`; `Variance (Abs)` → background colour scale (white → `#F8CBAD`, lowest = white); `Budget Consumption %` → data bars (navy). Row subtotals ON, grand total bold |
| 7 | **Clustered bar chart** | 272, 436, 480, 272 | Y: `Cost Centre[Cost Centre]`; X: `Variance % (P&L Impact)` | Sorted ascending (worst at top). Bar colour by field value `Variance Colour`. Data labels in %. Title "Variance % by cost centre (negative = over budget)" |
| 8 | **Decomposition tree** | 764, 436, 500, 272 | Analyze: `Variance (Abs)`; Explain by: `Cost Centre[Department]`, `Cost Centre[Cost Centre]`, `Account[P&L Group]`, `Account[Account]`, `Date[Quarter]` | Pre-expand: Department → Marketing → Cost Centre. Use *High value* AI split. Title "What drives the overrun?" |

**Drill-down:** in the matrix, *Expand all down one level* shows the P&L groups of each cost
centre. The expected story: **CC310 Marketing Benelux** is 15–22 % over budget every year,
mainly on advertising, digital marketing and headcount.

**Optional drill-through page** (nice extra): a hidden page "Cost Centre Detail" with
drill-through field `Cost Centre[Cost Centre]`, a monthly line chart (Actual, Budget,
Forecast) and a table by account.

---

## Page 3 – Data Quality

**Question it answers:** *"Can we trust these numbers?"* This page shows that every euro in
the ledger is either loaded or quarantined, with a reason.

The DQ tables have no relationship to `Date` (rejected rows may have *invalid* periods), so
turn off interactions from any synced year slicer (Format → Edit interactions → None).

| # | Visual type | Position (x, y, w, h) | Fields | Formatting |
|---|---|---|---|---|
| 1 | **Text box** | 16, 12, 1248, 40 | "Data quality – ledger checks and quarantine" | 18 pt bold navy |
| 2–6 | **Card (new)**, 5 cards | 16, 64, 1248, 110 | `Clean Row Rate %`, `Rejected Rows`, `Rejected Amount`, `DQ Checks Failed`, `DQ Checks Passed %` | `Clean Row Rate %` 1 dp; `Rejected Amount` in M |
| 7 | **Table** | 16, 186, 800, 300 | `DQ Results`: Check ID, Check Name, Check Category, Severity, Status, Rows Checked, Rows Affected, Pct Affected, Amount Affected, Sample Keys | `Status` → background colour by field value `DQ Status Colour`, white bold font. Sort by Check ID. Word wrap on Sample Keys. Title "Check results (ERROR = quarantined, WARNING = loaded & reported)" |
| 8 | **Clustered bar chart** | 828, 186, 436, 300 | Y: `Rejected Rows[Reject Reason]`; X: `Rejected Rows` | Sorted descending; bars red `#C62828`; data labels ON. Title "Rejected rows by check" |
| 9 | **Clustered column chart** | 16, 498, 600, 210 | X: `Rejected Rows[Period]`; Y: `Rejected Amount` | Sort by Period ascending. Title "Quarantined amount by source period". *Out-of-range periods (2020, 2026–2028) show wrongly booked periods at a glance* |
| 10 | **Table** | 628, 498, 636, 210 | `Rejected Rows`: Record Key, Document Ref, Posting Date, Period, Account Code, Cost Centre Code, Amount, Reject Reason | Filtered by clicking visual 7 or 8. Title "Quarantined records (drill to fix at source)" |

**Reconciliation proof:** checks **DQ16–DQ19** must show `PASS`. Mention in interviews: *ledger
total = loaded actuals + quarantined amount, to the cent.*

---

## Screenshots to take (for the README)

Save as PNG, about 1600 px wide, into `docs/images/`:

1. `executive_overview.png` – page 1 with FY2025 selected
2. `cost_centre_deep_dive.png` – page 2, matrix expanded to Marketing → CC310
3. `data_quality.png` – page 3
4. `model_view.png` – Model view (star schema diagram)
5. `excel_reconciliation.png` – Excel *Reconciliation* sheet showing "ALL OK"
