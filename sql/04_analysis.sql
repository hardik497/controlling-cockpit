-- =====================================================================================
-- 04_analysis.sql – analytical queries for controlling (CTEs + window functions)
-- -------------------------------------------------------------------------------------
-- Every query is a view so it can be reused by the CLI (make analysis), the tests and
-- ad-hoc SQL. Conventions:
--   * amount           natural sign (revenue and costs positive)
--   * amount_pnl       amount * dim_account.sign  (revenue +, costs -) -> sums to EBIT
--   * variance         actual - budget (natural sign)
--   * variance_pnl     (actual - budget) * sign  -> positive = favourable, negative = adverse
-- Division is guarded with NULLIF to avoid divide-by-zero (portable across dialects).
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- Base view: fact joined to all dimensions (one wide row per fact row)
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_finance AS
SELECT
    d.fiscal_year,
    d.fiscal_quarter,
    d.month_number,
    d.period,
    s.scenario,
    a.account_code,
    a.account_name,
    a.pnl_category,
    a.pnl_group,
    a.pnl_group_sort,
    a.sign,
    c.cost_centre_code,
    c.cost_centre_name,
    c.department,
    c.region,
    f.amount,
    f.amount * a.sign AS amount_pnl
FROM fact_finance AS f
JOIN dim_date        AS d ON d.date_key = f.date_key
JOIN dim_account     AS a ON a.account_key = f.account_key
JOIN dim_cost_centre AS c ON c.cost_centre_key = f.cost_centre_key
JOIN dim_scenario    AS s ON s.scenario_key = f.scenario_key;

-- -------------------------------------------------------------------------------------
-- 1. Budget vs. actual by department and fiscal year (income and expense separated,
--    because adding revenue and cost in one number is meaningless)
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_bva_department AS
WITH pivoted AS (
    SELECT
        fiscal_year,
        department,
        CASE WHEN sign = 1 THEN 'Income' ELSE 'Expense' END            AS account_type,
        MAX(sign)                                                      AS sign,
        SUM(CASE WHEN scenario = 'Actual'   THEN amount ELSE 0 END)    AS actual,
        SUM(CASE WHEN scenario = 'Budget'   THEN amount ELSE 0 END)    AS budget,
        SUM(CASE WHEN scenario = 'Forecast' THEN amount ELSE 0 END)    AS forecast
    FROM v_finance
    GROUP BY fiscal_year, department, CASE WHEN sign = 1 THEN 'Income' ELSE 'Expense' END
)
SELECT
    fiscal_year,
    department,
    account_type,
    ROUND(actual, 2)                                                   AS actual,
    ROUND(budget, 2)                                                   AS budget,
    ROUND(actual - budget, 2)                                          AS variance,
    ROUND(100.0 * (actual - budget) / NULLIF(budget, 0), 2)            AS variance_pct,
    CASE WHEN (actual - budget) * sign >= 0 THEN 'Favourable' ELSE 'Adverse' END
                                                                       AS assessment,
    ROUND(forecast, 2)                                                 AS forecast
FROM pivoted
ORDER BY fiscal_year, department, account_type;

-- -------------------------------------------------------------------------------------
-- 2. Budget vs. actual by cost centre (expenses only) with a rank per year
--    -> shows which cost centre is structurally over budget
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_bva_cost_centre AS
WITH cc AS (
    SELECT
        fiscal_year,
        cost_centre_code,
        cost_centre_name,
        department,
        SUM(CASE WHEN scenario = 'Actual' THEN amount ELSE 0 END) AS actual,
        SUM(CASE WHEN scenario = 'Budget' THEN amount ELSE 0 END) AS budget
    FROM v_finance
    WHERE sign = -1
    GROUP BY fiscal_year, cost_centre_code, cost_centre_name, department
)
SELECT
    fiscal_year,
    cost_centre_code,
    cost_centre_name,
    department,
    ROUND(actual, 2)                                         AS actual,
    ROUND(budget, 2)                                         AS budget,
    ROUND(actual - budget, 2)                                AS variance,
    ROUND(100.0 * (actual - budget) / NULLIF(budget, 0), 2)  AS variance_pct,
    RANK() OVER (PARTITION BY fiscal_year
                 ORDER BY (actual - budget) / NULLIF(budget, 0) DESC) AS overrun_rank
FROM cc
ORDER BY fiscal_year, overrun_rank;

-- -------------------------------------------------------------------------------------
-- 3. Year-over-year growth per P&L group (LAG window function)
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_yoy_growth AS
WITH yearly AS (
    SELECT fiscal_year, pnl_group, pnl_group_sort, SUM(amount) AS actual
    FROM v_finance
    WHERE scenario = 'Actual'
    GROUP BY fiscal_year, pnl_group, pnl_group_sort
)
SELECT
    fiscal_year,
    pnl_group,
    ROUND(actual, 2)                                                           AS actual,
    ROUND(LAG(actual) OVER (PARTITION BY pnl_group ORDER BY fiscal_year), 2)   AS actual_py,
    ROUND(100.0 * (actual - LAG(actual) OVER (PARTITION BY pnl_group ORDER BY fiscal_year))
          / NULLIF(LAG(actual) OVER (PARTITION BY pnl_group ORDER BY fiscal_year), 0), 2)
                                                                               AS yoy_pct
FROM yearly
ORDER BY pnl_group_sort, fiscal_year;

-- -------------------------------------------------------------------------------------
-- 4. Top 5 cost overruns per fiscal year (account x cost centre, absolute EUR)
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_top5_cost_overruns AS
WITH lines AS (
    SELECT
        fiscal_year,
        account_code,
        account_name,
        cost_centre_code,
        cost_centre_name,
        SUM(CASE WHEN scenario = 'Actual' THEN amount ELSE 0 END) AS actual,
        SUM(CASE WHEN scenario = 'Budget' THEN amount ELSE 0 END) AS budget
    FROM v_finance
    WHERE sign = -1
    GROUP BY fiscal_year, account_code, account_name, cost_centre_code, cost_centre_name
),
ranked AS (
    SELECT
        *,
        actual - budget AS overrun,
        ROW_NUMBER() OVER (PARTITION BY fiscal_year ORDER BY actual - budget DESC) AS rn
    FROM lines
)
SELECT
    fiscal_year,
    rn                                                        AS overrun_rank,
    account_code || ' ' || account_name                       AS account,
    cost_centre_code || ' ' || cost_centre_name               AS cost_centre,
    ROUND(actual, 2)                                          AS actual,
    ROUND(budget, 2)                                          AS budget,
    ROUND(overrun, 2)                                         AS overrun,
    ROUND(100.0 * overrun / NULLIF(budget, 0), 2)             AS overrun_pct
FROM ranked
WHERE rn <= 5
ORDER BY fiscal_year, rn;

-- -------------------------------------------------------------------------------------
-- 5. Running YTD totals per month (revenue and EBIT, actual vs. budget)
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_running_ytd AS
WITH monthly AS (
    SELECT
        fiscal_year,
        month_number,
        period,
        SUM(CASE WHEN scenario = 'Actual' AND sign = 1 THEN amount ELSE 0 END)     AS revenue_act,
        SUM(CASE WHEN scenario = 'Budget' AND sign = 1 THEN amount ELSE 0 END)     AS revenue_bud,
        SUM(CASE WHEN scenario = 'Actual' THEN amount_pnl ELSE 0 END)              AS ebit_act,
        SUM(CASE WHEN scenario = 'Budget' THEN amount_pnl ELSE 0 END)              AS ebit_bud
    FROM v_finance
    GROUP BY fiscal_year, month_number, period
)
SELECT
    fiscal_year,
    period,
    ROUND(revenue_act, 2)                                                           AS revenue_actual,
    ROUND(SUM(revenue_act) OVER w, 2)                                               AS revenue_actual_ytd,
    ROUND(SUM(revenue_bud) OVER w, 2)                                               AS revenue_budget_ytd,
    ROUND(SUM(ebit_act) OVER w, 2)                                                  AS ebit_actual_ytd,
    ROUND(SUM(ebit_bud) OVER w, 2)                                                  AS ebit_budget_ytd,
    ROUND(100.0 * (SUM(revenue_act) OVER w - SUM(revenue_bud) OVER w)
          / NULLIF(SUM(revenue_bud) OVER w, 0), 2)                                  AS revenue_ytd_variance_pct
FROM monthly
WINDOW w AS (PARTITION BY fiscal_year ORDER BY month_number
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
ORDER BY fiscal_year, period;

-- -------------------------------------------------------------------------------------
-- 6. Gross margin and operating (EBIT) margin per fiscal year and scenario
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_margins AS
WITH pl AS (
    SELECT
        fiscal_year,
        scenario,
        SUM(CASE WHEN pnl_category = 'Revenue'            THEN amount ELSE 0 END) AS revenue,
        SUM(CASE WHEN pnl_category = 'Cost of Goods Sold' THEN amount ELSE 0 END) AS cogs,
        SUM(CASE WHEN pnl_category = 'Operating Expenses' THEN amount ELSE 0 END) AS opex
    FROM v_finance
    GROUP BY fiscal_year, scenario
)
SELECT
    fiscal_year,
    scenario,
    ROUND(revenue, 2)                                              AS revenue,
    ROUND(cogs, 2)                                                 AS cogs,
    ROUND(revenue - cogs, 2)                                       AS gross_profit,
    ROUND(100.0 * (revenue - cogs) / NULLIF(revenue, 0), 2)        AS gross_margin_pct,
    ROUND(opex, 2)                                                 AS opex,
    ROUND(revenue - cogs - opex, 2)                                AS ebit,
    ROUND(100.0 * (revenue - cogs - opex) / NULLIF(revenue, 0), 2) AS ebit_margin_pct
FROM pl
ORDER BY fiscal_year, scenario;

-- -------------------------------------------------------------------------------------
-- 7. Forecast accuracy per fiscal year and P&L group: 1 - WAPE
--    WAPE = sum|Actual - Forecast| / sum|Actual| at month x account x cost-centre grain,
--    so over- and under-forecasts cannot cancel each other out.
--    Same definition as the DAX measure [Forecast Accuracy %].
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_forecast_accuracy AS
WITH grain AS (
    SELECT
        fiscal_year,
        pnl_group,
        pnl_group_sort,
        period,
        account_code,
        cost_centre_code,
        SUM(CASE WHEN scenario = 'Actual'   THEN amount ELSE 0 END) AS actual,
        SUM(CASE WHEN scenario = 'Forecast' THEN amount ELSE 0 END) AS forecast
    FROM v_finance
    GROUP BY fiscal_year, pnl_group, pnl_group_sort, period, account_code, cost_centre_code
)
SELECT
    fiscal_year,
    pnl_group,
    ROUND(SUM(actual), 2)                                                          AS actual,
    ROUND(SUM(forecast), 2)                                                        AS forecast,
    ROUND(100.0 * (1 - SUM(ABS(actual - forecast)) / NULLIF(SUM(ABS(actual)), 0)), 2)
                                                                                   AS forecast_accuracy_pct
FROM grain
GROUP BY fiscal_year, pnl_group, pnl_group_sort
ORDER BY fiscal_year, pnl_group_sort;
