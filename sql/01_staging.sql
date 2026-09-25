-- =====================================================================================
-- 01_staging.sql – load raw CSV files into staging tables
-- -------------------------------------------------------------------------------------
-- Staging tables mirror the source files 1:1 with explicit data types. No business
-- logic and no filtering happens here: every source row must arrive in staging so the
-- data-quality layer can see (and count) it.
--
-- ${RAW_DIR} is substituted by the Python runner (cockpit/warehouse.py).
-- Dialect note: read_csv() is DuckDB-specific. On SQL Server use BULK INSERT / OPENROWSET,
-- on PostgreSQL use COPY ... FROM ... WITH (FORMAT csv, HEADER true).
-- =====================================================================================

CREATE OR REPLACE TABLE stg_chart_of_accounts AS
SELECT *
FROM read_csv('${RAW_DIR}/chart_of_accounts.csv', header = true, columns = {
    'account_code':   'VARCHAR',
    'account_name':   'VARCHAR',
    'pnl_group':      'VARCHAR',
    'pnl_category':   'VARCHAR',
    'pnl_group_sort': 'INTEGER',
    'sign':           'INTEGER'
});

CREATE OR REPLACE TABLE stg_cost_centres AS
SELECT *
FROM read_csv('${RAW_DIR}/cost_centres.csv', header = true, columns = {
    'cost_centre_code': 'VARCHAR',
    'cost_centre_name': 'VARCHAR',
    'department':       'VARCHAR',
    'region':           'VARCHAR',
    'manager':          'VARCHAR'
});

-- Period is read as text on purpose: invalid periods must survive loading.
CREATE OR REPLACE TABLE stg_gl_actuals AS
SELECT *
FROM read_csv('${RAW_DIR}/gl_actuals.csv', header = true, columns = {
    'entry_id':         'VARCHAR',
    'document_ref':     'VARCHAR',
    'posting_date':     'DATE',
    'period':           'VARCHAR',
    'account_code':     'VARCHAR',
    'cost_centre_code': 'VARCHAR',
    'currency':         'VARCHAR',
    'amount':           'DECIMAL(18, 2)',
    'text':             'VARCHAR'
});

CREATE OR REPLACE TABLE stg_budget AS
SELECT *
FROM read_csv('${RAW_DIR}/budget.csv', header = true, columns = {
    'period':           'VARCHAR',
    'account_code':     'VARCHAR',
    'cost_centre_code': 'VARCHAR',
    'amount':           'DECIMAL(18, 2)'
});

CREATE OR REPLACE TABLE stg_forecast AS
SELECT *
FROM read_csv('${RAW_DIR}/forecast.csv', header = true, columns = {
    'period':           'VARCHAR',
    'account_code':     'VARCHAR',
    'cost_centre_code': 'VARCHAR',
    'amount':           'DECIMAL(18, 2)'
});
