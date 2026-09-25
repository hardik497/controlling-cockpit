-- =====================================================================================
-- 03_star_schema.sql – clean star schema + quarantine + post-load reconciliation
-- -------------------------------------------------------------------------------------
-- Grain of fact_finance: one row per month x account x cost centre x scenario.
--   * Actuals are aggregated from transaction level (GL) to month.
--   * Budget and Forecast arrive at month level already.
-- Amounts keep their natural sign (revenue and costs positive). The P&L sign lives in
-- dim_account.sign and is applied by the semantic model (DAX) and 04_analysis.sql.
--
-- Records that failed an ERROR-severity check in 02_data_quality.sql are NOT silently
-- dropped: they are written to fact_finance_rejected with the reason(s).
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- dim_date – daily calendar (Power BI needs contiguous dates to "mark as date table")
-- Fiscal year = calendar year for Nordwerk GmbH.
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_date AS
WITH days AS (
    SELECT CAST(d AS DATE) AS date
    FROM generate_series(DATE '2023-01-01', DATE '2025-12-31', INTERVAL 1 DAY) AS t(d)
)
SELECT
    CAST(strftime(date, '%Y%m%d') AS INTEGER)            AS date_key,
    date,
    EXTRACT(YEAR FROM date)                              AS fiscal_year,
    'FY' || CAST(EXTRACT(YEAR FROM date) AS VARCHAR)     AS fiscal_year_label,
    EXTRACT(QUARTER FROM date)                           AS fiscal_quarter,
    'Q' || CAST(EXTRACT(QUARTER FROM date) AS VARCHAR)   AS fiscal_quarter_label,
    'FY' || CAST(EXTRACT(YEAR FROM date) AS VARCHAR)
        || '-Q' || CAST(EXTRACT(QUARTER FROM date) AS VARCHAR) AS year_quarter,
    EXTRACT(MONTH FROM date)                             AS month_number,
    strftime(date, '%B')                                 AS month_name,
    strftime(date, '%b')                                 AS month_short,
    strftime(date, '%Y-%m')                              AS period,
    CAST(strftime(date, '%Y%m') AS INTEGER)              AS period_sort,
    CAST(date_trunc('month', date) AS DATE)              AS month_start,
    EXTRACT(DAY FROM date)                               AS day_of_month,
    strftime(date, '%A')                                 AS weekday_name,
    ISODOW(date)                                         AS weekday_number,
    ISODOW(date) >= 6                                    AS is_weekend
FROM days;

-- -------------------------------------------------------------------------------------
-- dim_account – P&L hierarchy: category > group > account
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_account AS
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY account_code) AS INTEGER) AS account_key,
    account_code,
    account_name,
    account_code || ' ' || account_name                  AS account_label,
    pnl_group,
    pnl_group_sort,
    pnl_category,
    CASE pnl_category
        WHEN 'Revenue'            THEN 1
        WHEN 'Cost of Goods Sold' THEN 2
        ELSE 3
    END                                                  AS pnl_category_sort,
    sign,
    CASE WHEN sign = 1 THEN 'Income' ELSE 'Expense' END  AS account_type
FROM stg_chart_of_accounts;

-- -------------------------------------------------------------------------------------
-- dim_cost_centre – department and region
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_cost_centre AS
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY cost_centre_code) AS INTEGER) AS cost_centre_key,
    cost_centre_code,
    cost_centre_name,
    cost_centre_code || ' ' || cost_centre_name          AS cost_centre_label,
    department,
    region,
    manager
FROM stg_cost_centres;

-- -------------------------------------------------------------------------------------
-- dim_scenario
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_scenario (
    scenario_key  INTEGER NOT NULL PRIMARY KEY,
    scenario      VARCHAR NOT NULL,
    scenario_sort INTEGER NOT NULL,
    description   VARCHAR NOT NULL
);
INSERT INTO dim_scenario VALUES
    (1, 'Actual',   1, 'Booked general-ledger actuals after data-quality checks'),
    (2, 'Budget',   2, 'Approved annual budget, phased monthly'),
    (3, 'Forecast', 3, 'Latest rolling forecast');

-- -------------------------------------------------------------------------------------
-- Helper: records rejected by at least one ERROR check, with all reasons
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TEMP TABLE tmp_rejections AS
SELECT
    f.source_table,
    f.record_key,
    MIN(f.check_id)                                            AS reject_check_id,
    string_agg(DISTINCT f.check_id, ', ' ORDER BY f.check_id)  AS all_check_ids
FROM dq_row_flags AS f
JOIN dq_check_catalog AS c ON c.check_id = f.check_id
WHERE c.severity = 'ERROR'
GROUP BY f.source_table, f.record_key;

-- -------------------------------------------------------------------------------------
-- fact_finance
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_finance AS
WITH clean_actuals AS (
    SELECT g.period, g.account_code, g.cost_centre_code, g.amount
    FROM stg_gl_actuals AS g
    LEFT JOIN tmp_rejections AS r
        ON r.source_table = 'stg_gl_actuals' AND r.record_key = g.entry_id
    WHERE r.record_key IS NULL
),
clean_plan AS (
    SELECT 2 AS scenario_key, 'stg_budget' AS source_table, b.*
    FROM stg_budget AS b
    UNION ALL
    SELECT 3, 'stg_forecast', f.*
    FROM stg_forecast AS f
),
unioned AS (
    SELECT 1 AS scenario_key, period, account_code, cost_centre_code,
           SUM(amount) AS amount, COUNT(*) AS line_count
    FROM clean_actuals
    GROUP BY period, account_code, cost_centre_code
    UNION ALL
    SELECT p.scenario_key, p.period, p.account_code, p.cost_centre_code, p.amount, 1
    FROM clean_plan AS p
    LEFT JOIN tmp_rejections AS r
        ON r.source_table = p.source_table
       AND r.record_key = p.period || '|' || p.account_code || '|' || p.cost_centre_code
    WHERE r.record_key IS NULL
)
SELECT
    CAST(REPLACE(u.period, '-', '') || '01' AS INTEGER)  AS date_key,
    a.account_key,
    c.cost_centre_key,
    u.scenario_key,
    CAST(u.amount AS DECIMAL(18, 2))                     AS amount,
    CAST(u.line_count AS INTEGER)                        AS line_count
FROM unioned AS u
JOIN dim_account     AS a ON a.account_code = u.account_code
JOIN dim_cost_centre AS c ON c.cost_centre_code = u.cost_centre_code
ORDER BY date_key, account_key, cost_centre_key, scenario_key;

-- -------------------------------------------------------------------------------------
-- fact_finance_rejected – quarantine (source columns + reason)
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_finance_rejected AS
SELECT
    'Actual'                  AS scenario,
    r.source_table,
    r.record_key,
    g.document_ref,
    g.posting_date,
    g.period,
    g.account_code,
    g.cost_centre_code,
    g.amount,
    r.reject_check_id,
    cat.check_name            AS reject_reason,
    r.all_check_ids,
    CAST(date_trunc('second', CURRENT_TIMESTAMP) AS TIMESTAMP)         AS rejected_at
FROM tmp_rejections AS r
JOIN stg_gl_actuals AS g ON g.entry_id = r.record_key
JOIN dq_check_catalog AS cat ON cat.check_id = r.reject_check_id
WHERE r.source_table = 'stg_gl_actuals'
UNION ALL
SELECT
    CASE p.source_table WHEN 'stg_budget' THEN 'Budget' ELSE 'Forecast' END,
    r.source_table,
    r.record_key,
    NULL,
    NULL,
    p.period,
    p.account_code,
    p.cost_centre_code,
    p.amount,
    r.reject_check_id,
    cat.check_name,
    r.all_check_ids,
    CAST(date_trunc('second', CURRENT_TIMESTAMP) AS TIMESTAMP)
FROM tmp_rejections AS r
JOIN (
    SELECT 'stg_budget' AS source_table, * FROM stg_budget
    UNION ALL
    SELECT 'stg_forecast', * FROM stg_forecast
) AS p
    ON p.source_table = r.source_table
   AND p.period || '|' || p.account_code || '|' || p.cost_centre_code = r.record_key
JOIN dq_check_catalog AS cat ON cat.check_id = r.reject_check_id;

-- -------------------------------------------------------------------------------------
-- Post-load reconciliation (appended to dq_results)
--   DQ17 amount:  staged GL total  = fact Actual total + rejected Actual total
--   DQ18 rows:    staged GL rows   = GL lines in fact  + rejected Actual rows
--   DQ19 budget:  staged budget    = fact Budget total + rejected Budget total
-- -------------------------------------------------------------------------------------
INSERT INTO dq_results
WITH t AS (
    SELECT
        (SELECT SUM(amount) FROM stg_gl_actuals)                                AS stg_amt,
        (SELECT COUNT(*)    FROM stg_gl_actuals)                                AS stg_rows,
        (SELECT SUM(amount) FROM fact_finance WHERE scenario_key = 1)           AS fact_amt,
        (SELECT SUM(line_count) FROM fact_finance WHERE scenario_key = 1)       AS fact_rows,
        (SELECT COALESCE(SUM(amount), 0) FROM fact_finance_rejected
          WHERE scenario = 'Actual')                                            AS rej_amt,
        (SELECT COUNT(*) FROM fact_finance_rejected WHERE scenario = 'Actual')  AS rej_rows,
        (SELECT SUM(amount) FROM stg_budget)                                    AS stg_bud,
        (SELECT SUM(amount) FROM fact_finance WHERE scenario_key = 2)           AS fact_bud,
        (SELECT COALESCE(SUM(amount), 0) FROM fact_finance_rejected
          WHERE scenario = 'Budget')                                            AS rej_bud
)
SELECT 'DQ17', 'fact_vs_ledger_amount_reconciliation', 'Reconciliation', 'fact_finance',
       'ERROR', stg_rows,
       CASE WHEN stg_amt = fact_amt + rej_amt THEN 0 ELSE 1 END, 0.0,
       CAST(stg_amt - fact_amt - rej_amt AS DECIMAL(18, 2)),
       CASE WHEN stg_amt = fact_amt + rej_amt THEN 'PASS' ELSE 'FAIL' END,
       'ledger=' || CAST(stg_amt AS VARCHAR) || ' fact=' || CAST(fact_amt AS VARCHAR)
           || ' rejected=' || CAST(rej_amt AS VARCHAR),
       'Ledger total equals loaded Actual plus quarantined Actual', CAST(date_trunc('second', CURRENT_TIMESTAMP) AS TIMESTAMP)
FROM t
UNION ALL
SELECT 'DQ18', 'fact_vs_ledger_row_reconciliation', 'Reconciliation', 'fact_finance',
       'ERROR', stg_rows,
       CASE WHEN stg_rows = fact_rows + rej_rows THEN 0 ELSE 1 END, 0.0,
       CAST(0 AS DECIMAL(18, 2)),
       CASE WHEN stg_rows = fact_rows + rej_rows THEN 'PASS' ELSE 'FAIL' END,
       'ledger_rows=' || CAST(stg_rows AS VARCHAR) || ' fact_lines='
           || CAST(fact_rows AS VARCHAR) || ' rejected_rows=' || CAST(rej_rows AS VARCHAR),
       'Every ledger row is either loaded (line_count) or quarantined', CAST(date_trunc('second', CURRENT_TIMESTAMP) AS TIMESTAMP)
FROM t
UNION ALL
SELECT 'DQ19', 'fact_vs_budget_amount_reconciliation', 'Reconciliation', 'fact_finance',
       'ERROR', (SELECT COUNT(*) FROM stg_budget),
       CASE WHEN stg_bud = fact_bud + rej_bud THEN 0 ELSE 1 END, 0.0,
       CAST(stg_bud - fact_bud - rej_bud AS DECIMAL(18, 2)),
       CASE WHEN stg_bud = fact_bud + rej_bud THEN 'PASS' ELSE 'FAIL' END,
       'budget=' || CAST(stg_bud AS VARCHAR) || ' fact=' || CAST(fact_bud AS VARCHAR),
       'Budget file total equals loaded Budget plus quarantined Budget', CAST(date_trunc('second', CURRENT_TIMESTAMP) AS TIMESTAMP)
FROM t;
