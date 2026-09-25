# Microsoft Copilot in controlling: a hands-on evaluation

> **Status: TEMPLATE, not filled in yet.** I fill every result cell myself after testing
> Copilot on this project's data. Nothing below is a Copilot result until I write it in.

## 1. Why this evaluation

Controlling teams are asked whether Copilot can speed up reporting and variance analysis.
A number that *sounds* plausible but is wrong is worse than no number. So every Copilot
answer here is checked against a **verified value** from the SQL warehouse, the Excel
reconciliation or a DAX query I wrote myself.

## 2. Test setup

| Item | Value |
|---|---|
| Date(s) tested | |
| Copilot product(s) (Power BI Copilot / Copilot in Excel / Microsoft 365 Copilot Chat) | |
| Licence / capacity (e.g. Fabric F64, Copilot Pro) | |
| Power BI Desktop version | |
| Excel version | |
| Model state (commit hash of this repo) | |
| Language of prompts | |
| Linguistic schema / Q&A synonyms prepared? (yes/no) | |
| Measure descriptions present in model? | Yes, all 39 measures have descriptions |

### Where the verified values come from

| Source | How to get it |
|---|---|
| SQL views | `make analysis` or query `data/warehouse.duckdb` (`v_margins`, `v_bva_department`, `v_bva_cost_centre`, `v_top5_cost_overruns`, `v_yoy_growth`, `v_forecast_accuracy`) |
| Excel | `excel/controlling_reconciliation.xlsx` → *Summary* (set fiscal year in C4) |
| Power BI | DAX query view: `EVALUATE SUMMARIZECOLUMNS(...)` with the model measures |

## 3. Scoring rubric

| Score | Meaning |
|---|---|
| **Correct** | Number or statement matches the verified value (rounding tolerance ±0.1 % or ±€1k) |
| **Partially correct** | Right direction or approach, but a wrong filter, period, sign or detail |
| **Wrong** | Wrong number, wrong logic, or a made-up explanation (hallucination) |
| **Refused / no answer** | Copilot could not answer |

Time saved = (time I need without Copilot) − (time with Copilot, **including verification**).

## 4. Suggested test prompts (10)

| # | Area | Prompt |
|---|---|---|
| P01 | DAX authoring | "Write a DAX measure for Variance % that compares Actual to Budget and handles division by zero." |
| P02 | DAX authoring | "Create a year-to-date measure for Actual using the Date table." |
| P03 | DAX explanation | "Explain what the measure [Forecast Accuracy %] calculates and why it uses SUMX over a SUMMARIZE." |
| P04 | Report summary | "Summarise the variance on the Executive Overview page for FY2025 in three bullet points for the CFO." |
| P05 | Root cause | "Explain why Marketing is over budget in FY2025." |
| P06 | Ranking | "Which five account and cost-centre combinations have the largest cost overruns in FY2024?" |
| P07 | KPI Q&A | "What was the gross margin in FY2024 compared to budget, and what caused the difference?" |
| P08 | Data quality | "How many ledger rows were rejected by data-quality checks and what are the main reasons?" |
| P09 | Excel | "In the Summary sheet, add a column that shows the variance in percent and highlight values above 5 % in red." |
| P10 | Visual creation | "Create a matrix showing Actual, Budget and Variance % by department and cost centre with conditional formatting." |

## 5. Results log

One row per prompt run. If a prompt needs follow-ups, log each attempt as P05a, P05b, ...

| # | Prompt (as sent) | Copilot output (summary, or link to screenshot in `docs/images/copilot/`) | Verified correct value | How verified | Correct? (Correct / Partial / Wrong / Refused) | Time without Copilot (min) | Time with Copilot incl. checking (min) | Time saved (min) | Risks / limitations observed |
|---|---|---|---|---|---|---|---|---|---|
| P01 | | | | | | | | | |
| P02 | | | | | | | | | |
| P03 | | | | | | | | | |
| P04 | | | | | | | | | |
| P05 | | | | | | | | | |
| P06 | | | | | | | | | |
| P07 | | | | | | | | | |
| P08 | | | | | | | | | |
| P09 | | | | | | | | | |
| P10 | | | | | | | | | |

## 6. Summary scorecard

| Metric | Value |
|---|---|
| Prompts tested | |
| Correct | |
| Partially correct | |
| Wrong | |
| Refused / no answer | |
| Total time saved (min) | |
| Answers that would have been dangerous to use without checking | |

## 7. Observations by category

### 7.1 DAX and formula authoring (P01–P03, P09)

-

### 7.2 Narrative summaries and root-cause explanations (P04, P05, P07)

-

### 7.3 Numeric Q&A and ranking (P06, P08)

-

### 7.4 Visual creation (P10)

-

## 8. Risks and limitations

Things to check for while testing (write what actually happened):

- [ ] Sign logic: does Copilot understand that a positive cost variance is *adverse*?
- [ ] Filter context: does it respect the selected fiscal year or department?
- [ ] Hallucinated causes: does it invent reasons that are not in the data?
- [ ] Quarantined data: does it know that rejected rows are *not* in Actual?
- [ ] Reproducibility: same prompt twice, same answer?
- [ ] Data privacy / governance: which data leaves the tenant, and what are the licence requirements?

Findings:

-

## 9. Conclusion: where Copilot really helps in controlling

**Helps (use it):**

-

**Use with care (always verify):**

-

**Don't use it for:**

-

**My recommendation for a controlling team:**

>
