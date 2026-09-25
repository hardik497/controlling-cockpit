# SQL dialect notes: DuckDB vs. SQL Server vs. PostgreSQL

The SQL is written close to ANSI SQL: CTEs, window functions (`ROW_NUMBER`, `RANK`, `LAG`,
`SUM() OVER`), `CASE`, `NULLIF`, `COALESCE`, `LEFT JOIN … IS NULL` anti-joins, and no
vendor-specific `QUALIFY`. It was written for DuckDB and has **not** been run on SQL Server
or PostgreSQL. To port it, change only the following:

| Construct used | DuckDB (as written) | SQL Server (T-SQL) | PostgreSQL |
|---|---|---|---|
| Load CSV | `read_csv('file.csv', columns = {...})` | `BULK INSERT` / `OPENROWSET(BULK …)` | `COPY t FROM 'file.csv' WITH (FORMAT csv, HEADER true)` |
| Create table from query | `CREATE OR REPLACE TABLE t AS SELECT …` | `DROP TABLE IF EXISTS t; SELECT … INTO t FROM …` | `DROP TABLE IF EXISTS t; CREATE TABLE t AS SELECT …` |
| Create/replace view | `CREATE OR REPLACE VIEW` | `CREATE OR ALTER VIEW` | `CREATE OR REPLACE VIEW` |
| Date → `YYYY-MM` | `strftime(d, '%Y-%m')` | `FORMAT(d, 'yyyy-MM')` | `to_char(d, 'YYYY-MM')` |
| Month/day series | `generate_series(DATE '2023-01-01', DATE '2025-12-31', INTERVAL 1 DAY)` | `GENERATE_SERIES` (2022+) + `DATEADD`, or a numbers/tally table | `generate_series(date '2023-01-01', date '2025-12-31', interval '1 day')` |
| Truncate to month | `date_trunc('month', d)` | `DATETRUNC(month, d)` (2022+) / `DATEFROMPARTS(YEAR(d), MONTH(d), 1)` | `date_trunc('month', d)` |
| ISO weekday | `ISODOW(d)` | `(DATEPART(weekday, d) + @@DATEFIRST - 2) % 7 + 1` | `EXTRACT(ISODOW FROM d)` |
| String concat | `a \|\| b` | `a + b` or `CONCAT(a, b)` | `a \|\| b` |
| Ordered string aggregation | `string_agg(x, ', ' ORDER BY x)` | `STRING_AGG(x, ', ') WITHIN GROUP (ORDER BY x)` | `string_agg(x, ', ' ORDER BY x)` |
| `string_agg(DISTINCT …)` | supported | not supported: aggregate a `SELECT DISTINCT` subquery | supported |
| Named window | `WINDOW w AS (…)` | not supported before 2022: repeat the `OVER (…)` | supported |
| `GROUP BY ALL` (tests only) | supported | list the columns | list the columns |
| Boolean column | `BOOLEAN` | `BIT` | `BOOLEAN` |
| Temp table | `CREATE TEMP TABLE` | `#tmp` | `CREATE TEMP TABLE` |
| Integer division | `/` always returns a decimal | `/` on integers truncates → write `100.0 * …` (already done) | same as SQL Server (already handled) |

Every percentage in the scripts is written as `100.0 * a / NULLIF(b, 0)`, so it behaves the
same way in all three engines.
