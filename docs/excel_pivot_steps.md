# Build the pivot table in Excel (about 2 minutes)

**Why this is manual:** `openpyxl` can keep pivot tables that already exist in a workbook,
but it cannot *create* a native pivot table (the pivot cache and pivot definition XML). So
the workbook ships with a clean source table, `tblFinance` on the **Data** sheet, and you
add the pivot table yourself. This is also a good thing to show live in an interview.

## Steps (Excel for Mac or Windows)

1. Open `excel/controlling_reconciliation.xlsx` and go to the **Data** sheet.
2. Click any cell in the table → **Insert → PivotTable** → the source shows `tblFinance`
   → choose **New Worksheet** → **OK**. Rename the new sheet to **Pivot**.
3. In the PivotTable Fields pane, drag:

   | Area | Field |
   |---|---|
   | Filters | `Fiscal year` (select **2025**), `P&L category` (select all *except* Revenue for a cost view) |
   | Rows | `Department`, then `Cost centre name` |
   | Columns | `Scenario` |
   | Values | `Amount` (Sum) |

4. Format the values: right-click a value → **Value Field Settings → Number Format →
   Number, 0 decimals, use 1000 separator**.
5. Add the variance: **PivotTable Analyze → Fields, Items & Sets → Calculated Item…** on the
   *Scenario* field → name `Variance`, formula `= Actual - Budget` → **Add**.
   (Optional: a second calculated item `Variance %` with `=(Actual-Budget)/Budget`, formatted as %.)
6. Hide *Forecast* in the column filter if you only want Actual vs. Budget.
7. **Design → Report Layout → Show in Tabular Form**, and **Design → Grand Totals → On for
   Rows Only**.
8. Optional: **Insert → Slicer → Region** for a one-click regional filter.

## What you should see (FY2025, costs)

The *Marketing* department is over budget, and *Marketing Benelux* has the largest variance.
Check that your pivot's grand total for Actual equals **Summary!C12** (total costs for the
selected year). If it does, the pivot and the formula-based summary agree.

## Tip: refreshing after `make excel`

`make excel` rebuilds the workbook from scratch, which removes a manually added pivot. If
you want to keep the pivot, copy the workbook first (e.g. `controlling_reconciliation_pivot.xlsx`),
or record the steps above as a macro.
