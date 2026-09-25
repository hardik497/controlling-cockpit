-- =====================================================================================
-- 02_data_quality.sql – data-quality checks on the staging layer
-- -------------------------------------------------------------------------------------
-- Pattern:
--   1. dq_check_catalog  – one row per check (id, category, severity, description).
--   2. dq_row_flags      – one row per (record, failed check). Row-level evidence.
--   3. dq_results        – catalog LEFT JOIN aggregated flags, so passing checks are
--                          reported with 0 rows affected (a check that ran and found
--                          nothing is information, too).
--
-- Severity rules:
--   ERROR   -> the record is quarantined in fact_finance_rejected (see 03_star_schema.sql)
--   WARNING -> the record is reported but still loaded
--
-- Dialect notes (see docs/sql_dialect_notes.md):
--   * strftime()        -> SQL Server: FORMAT(d, 'yyyy-MM'); PostgreSQL: to_char(d, 'YYYY-MM')
--   * generate_series() -> SQL Server 2022: GENERATE_SERIES(); earlier: a numbers table
--   * string_agg(... ORDER BY ...) -> SQL Server: STRING_AGG(...) WITHIN GROUP (ORDER BY ...)
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- Reference: valid fiscal periods (FY2023 – FY2025, fiscal year = calendar year)
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE ref_fiscal_periods AS
SELECT strftime(CAST(month_start AS DATE), '%Y-%m') AS period
FROM generate_series(DATE '2023-01-01', DATE '2025-12-01', INTERVAL 1 MONTH) AS t(month_start);

-- -------------------------------------------------------------------------------------
-- 1. Check catalog
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dq_check_catalog (
    check_id       VARCHAR NOT NULL PRIMARY KEY,
    check_name     VARCHAR NOT NULL,
    check_category VARCHAR NOT NULL,
    source_table   VARCHAR NOT NULL,
    severity       VARCHAR NOT NULL,
    description    VARCHAR NOT NULL
);

INSERT INTO dq_check_catalog VALUES
    ('DQ01', 'gl_duplicate_booking',      'Duplicates',          'stg_gl_actuals', 'ERROR',
     'Same document_ref, account and amount posted more than once; later entry_id is the duplicate'),
    ('DQ02', 'gl_missing_cost_centre',    'Mandatory fields',    'stg_gl_actuals', 'ERROR',
     'Cost centre is NULL or empty'),
    ('DQ03', 'gl_null_mandatory_fields',  'Mandatory fields',    'stg_gl_actuals', 'ERROR',
     'entry_id, posting_date, period, account_code or amount is NULL'),
    ('DQ04', 'gl_unknown_account',        'Orphan keys',         'stg_gl_actuals', 'ERROR',
     'Account code does not exist in the chart of accounts'),
    ('DQ05', 'gl_unknown_cost_centre',    'Orphan keys',         'stg_gl_actuals', 'ERROR',
     'Cost centre code does not exist in the cost-centre master'),
    ('DQ06', 'gl_revenue_negative_sign',  'Sign plausibility',   'stg_gl_actuals', 'ERROR',
     'Revenue posted with a negative amount (natural sign of revenue is positive)'),
    ('DQ07', 'gl_cost_negative_sign',     'Sign plausibility',   'stg_gl_actuals', 'WARNING',
     'Cost posted with a negative amount – may be a legitimate credit note, review'),
    ('DQ08', 'gl_invalid_period',         'Period validity',     'stg_gl_actuals', 'ERROR',
     'Period outside FY2023-FY2025 or not matching the month of the posting date'),
    ('DQ09', 'gl_foreign_currency',       'Consistency',         'stg_gl_actuals', 'ERROR',
     'Currency is not EUR (no FX conversion implemented)'),
    ('DQ10', 'budget_orphan_keys',        'Orphan keys',         'stg_budget',     'ERROR',
     'Budget line references an unknown account or cost centre'),
    ('DQ11', 'budget_duplicate_grain',    'Duplicates',          'stg_budget',     'ERROR',
     'More than one budget line per period, account and cost centre'),
    ('DQ12', 'budget_invalid_period',     'Period validity',     'stg_budget',     'ERROR',
     'Budget period outside FY2023-FY2025'),
    ('DQ13', 'forecast_orphan_keys',      'Orphan keys',         'stg_forecast',   'ERROR',
     'Forecast line references an unknown account or cost centre'),
    ('DQ14', 'forecast_duplicate_grain',  'Duplicates',          'stg_forecast',   'ERROR',
     'More than one forecast line per period, account and cost centre'),
    ('DQ15', 'forecast_invalid_period',   'Period validity',     'stg_forecast',   'ERROR',
     'Forecast period outside FY2023-FY2025');

-- -------------------------------------------------------------------------------------
-- 2. Row-level flags
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dq_row_flags (
    check_id     VARCHAR        NOT NULL,
    source_table VARCHAR        NOT NULL,
    record_key   VARCHAR,
    amount       DECIMAL(18, 2)
);

-- DQ01 duplicates: keep the first posting, flag every later one.
INSERT INTO dq_row_flags
WITH ranked AS (
    SELECT
        entry_id,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY document_ref, account_code, amount
            ORDER BY entry_id
        ) AS rn
    FROM stg_gl_actuals
)
SELECT 'DQ01', 'stg_gl_actuals', entry_id, amount
FROM ranked
WHERE rn > 1;

-- DQ02 missing cost centre
INSERT INTO dq_row_flags
SELECT 'DQ02', 'stg_gl_actuals', entry_id, amount
FROM stg_gl_actuals
WHERE cost_centre_code IS NULL OR TRIM(cost_centre_code) = '';

-- DQ03 other mandatory fields
INSERT INTO dq_row_flags
SELECT 'DQ03', 'stg_gl_actuals', entry_id, amount
FROM stg_gl_actuals
WHERE entry_id IS NULL
   OR posting_date IS NULL
   OR period IS NULL
   OR account_code IS NULL
   OR amount IS NULL;

-- DQ04 orphan account
INSERT INTO dq_row_flags
SELECT 'DQ04', 'stg_gl_actuals', g.entry_id, g.amount
FROM stg_gl_actuals AS g
LEFT JOIN stg_chart_of_accounts AS a ON a.account_code = g.account_code
WHERE g.account_code IS NOT NULL AND a.account_code IS NULL;

-- DQ05 orphan cost centre (NULLs are handled by DQ02)
INSERT INTO dq_row_flags
SELECT 'DQ05', 'stg_gl_actuals', g.entry_id, g.amount
FROM stg_gl_actuals AS g
LEFT JOIN stg_cost_centres AS c ON c.cost_centre_code = g.cost_centre_code
WHERE g.cost_centre_code IS NOT NULL
  AND TRIM(g.cost_centre_code) <> ''
  AND c.cost_centre_code IS NULL;

-- DQ06 / DQ07 sign plausibility (only for accounts we know)
INSERT INTO dq_row_flags
SELECT
    CASE WHEN a.pnl_group = 'Revenue' THEN 'DQ06' ELSE 'DQ07' END,
    'stg_gl_actuals',
    g.entry_id,
    g.amount
FROM stg_gl_actuals AS g
JOIN stg_chart_of_accounts AS a ON a.account_code = g.account_code
WHERE g.amount < 0;

-- DQ08 period validity: must be a known fiscal period AND match the posting date
INSERT INTO dq_row_flags
SELECT 'DQ08', 'stg_gl_actuals', g.entry_id, g.amount
FROM stg_gl_actuals AS g
LEFT JOIN ref_fiscal_periods AS p ON p.period = g.period
WHERE g.period IS NOT NULL
  AND (p.period IS NULL OR g.period <> strftime(g.posting_date, '%Y-%m'));

-- DQ09 currency
INSERT INTO dq_row_flags
SELECT 'DQ09', 'stg_gl_actuals', entry_id, amount
FROM stg_gl_actuals
WHERE currency IS NULL OR currency <> 'EUR';

-- DQ10 – DQ15: plan data (budget / forecast). Record key = period|account|cost centre.
INSERT INTO dq_row_flags
SELECT 'DQ10', 'stg_budget', b.period || '|' || b.account_code || '|' || b.cost_centre_code,
       b.amount
FROM stg_budget AS b
LEFT JOIN stg_chart_of_accounts AS a ON a.account_code = b.account_code
LEFT JOIN stg_cost_centres AS c ON c.cost_centre_code = b.cost_centre_code
WHERE a.account_code IS NULL OR c.cost_centre_code IS NULL;

INSERT INTO dq_row_flags
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY period, account_code, cost_centre_code ORDER BY amount
    ) AS rn
    FROM stg_budget
)
SELECT 'DQ11', 'stg_budget', period || '|' || account_code || '|' || cost_centre_code, amount
FROM ranked
WHERE rn > 1;

INSERT INTO dq_row_flags
SELECT 'DQ12', 'stg_budget', b.period || '|' || b.account_code || '|' || b.cost_centre_code,
       b.amount
FROM stg_budget AS b
LEFT JOIN ref_fiscal_periods AS p ON p.period = b.period
WHERE p.period IS NULL;

INSERT INTO dq_row_flags
SELECT 'DQ13', 'stg_forecast', f.period || '|' || f.account_code || '|' || f.cost_centre_code,
       f.amount
FROM stg_forecast AS f
LEFT JOIN stg_chart_of_accounts AS a ON a.account_code = f.account_code
LEFT JOIN stg_cost_centres AS c ON c.cost_centre_code = f.cost_centre_code
WHERE a.account_code IS NULL OR c.cost_centre_code IS NULL;

INSERT INTO dq_row_flags
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY period, account_code, cost_centre_code ORDER BY amount
    ) AS rn
    FROM stg_forecast
)
SELECT 'DQ14', 'stg_forecast', period || '|' || account_code || '|' || cost_centre_code, amount
FROM ranked
WHERE rn > 1;

INSERT INTO dq_row_flags
SELECT 'DQ15', 'stg_forecast', f.period || '|' || f.account_code || '|' || f.cost_centre_code,
       f.amount
FROM stg_forecast AS f
LEFT JOIN ref_fiscal_periods AS p ON p.period = f.period
WHERE p.period IS NULL;

-- -------------------------------------------------------------------------------------
-- 3. Aggregated results
-- -------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dq_results AS
WITH agg AS (
    SELECT
        check_id,
        COUNT(*)                        AS rows_affected,
        SUM(amount)                     AS amount_affected
    FROM dq_row_flags
    GROUP BY check_id
),
samples AS (
    -- first five keys per check as evidence for the analyst
    SELECT check_id, string_agg(record_key, ', ' ORDER BY record_key) AS sample_keys
    FROM (
        SELECT check_id, record_key,
               ROW_NUMBER() OVER (PARTITION BY check_id ORDER BY record_key) AS rn
        FROM dq_row_flags
    ) AS ranked
    WHERE rn <= 5
    GROUP BY check_id
),
source_rows AS (
    SELECT 'stg_gl_actuals' AS source_table, COUNT(*) AS rows_checked FROM stg_gl_actuals
    UNION ALL SELECT 'stg_budget',   COUNT(*) FROM stg_budget
    UNION ALL SELECT 'stg_forecast', COUNT(*) FROM stg_forecast
)
SELECT
    c.check_id,
    c.check_name,
    c.check_category,
    c.source_table,
    c.severity,
    s.rows_checked,
    COALESCE(a.rows_affected, 0)                               AS rows_affected,
    ROUND(100.0 * COALESCE(a.rows_affected, 0) / s.rows_checked, 3) AS pct_affected,
    CAST(COALESCE(a.amount_affected, 0) AS DECIMAL(18, 2))     AS amount_affected,
    CASE
        WHEN COALESCE(a.rows_affected, 0) = 0 THEN 'PASS'
        WHEN c.severity = 'ERROR'             THEN 'FAIL'
        ELSE 'WARN'
    END                                                        AS status,
    sm.sample_keys,
    c.description,
    CAST(date_trunc('second', CURRENT_TIMESTAMP) AS TIMESTAMP)  AS checked_at
FROM dq_check_catalog AS c
JOIN source_rows AS s ON s.source_table = c.source_table
LEFT JOIN agg AS a ON a.check_id = c.check_id
LEFT JOIN samples AS sm ON sm.check_id = c.check_id;

-- -------------------------------------------------------------------------------------
-- DQ16 pre-load control total: every staged GL euro is either clean or flagged.
-- Guards against rows being lost between staging and the check layer.
-- -------------------------------------------------------------------------------------
INSERT INTO dq_results
WITH flagged AS (
    SELECT DISTINCT f.record_key
    FROM dq_row_flags AS f
    JOIN dq_check_catalog AS c ON c.check_id = f.check_id
    WHERE f.source_table = 'stg_gl_actuals' AND c.severity = 'ERROR'
),
split AS (
    SELECT
        SUM(g.amount)                                                   AS total_staged,
        SUM(CASE WHEN f.record_key IS NULL THEN g.amount ELSE 0 END)    AS total_clean,
        SUM(CASE WHEN f.record_key IS NOT NULL THEN g.amount ELSE 0 END) AS total_flagged,
        COUNT(*)                                                        AS rows_checked
    FROM stg_gl_actuals AS g
    LEFT JOIN flagged AS f ON f.record_key = g.entry_id
)
SELECT
    'DQ16',
    'gl_control_total_preload',
    'Reconciliation',
    'stg_gl_actuals',
    'ERROR',
    rows_checked,
    CASE WHEN total_staged = total_clean + total_flagged THEN 0 ELSE 1 END,
    0.0,
    CAST(total_staged - total_clean - total_flagged AS DECIMAL(18, 2)),
    CASE WHEN total_staged = total_clean + total_flagged THEN 'PASS' ELSE 'FAIL' END,
    'staged=' || CAST(total_staged AS VARCHAR)
        || ' clean=' || CAST(total_clean AS VARCHAR)
        || ' flagged=' || CAST(total_flagged AS VARCHAR),
    'Staged ledger total equals clean total plus flagged (to-be-quarantined) total',
    CAST(date_trunc('second', CURRENT_TIMESTAMP) AS TIMESTAMP)
FROM split;
