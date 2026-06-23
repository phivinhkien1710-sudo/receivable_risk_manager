-- Clean Kaggle invoice-payment dataset for receivables risk experiments.
--
-- This script intentionally writes only to a local SQLite database under ml/data/.
-- It does not touch the ERPNext/Frappe site database.

.bail on

DROP TABLE IF EXISTS invoice_raw;

-- Step 1: Load the CSV exactly as received.
-- Everything is TEXT here so the import cannot silently coerce bad values.
CREATE TABLE invoice_raw (
    business_code TEXT,
    customer_id_raw TEXT,
    customer_name_raw TEXT,
    clear_date_raw TEXT,
    business_year_raw TEXT,
    doc_id_raw TEXT,
    posting_date_raw TEXT,
    document_create_date_raw TEXT,
    document_create_date_1_raw TEXT,
    due_date_raw TEXT,
    invoice_currency_raw TEXT,
    document_type_raw TEXT,
    posting_id_raw TEXT,
    area_business_raw TEXT,
    invoice_amount_raw TEXT,
    baseline_create_date_raw TEXT,
    payment_terms_raw TEXT,
    invoice_id_raw TEXT,
    is_open_raw TEXT
);

.mode csv
.import --skip 1 "/Users/phikien/Downloads/dataset.csv" invoice_raw

DROP TABLE IF EXISTS invoice_normalized;

-- Step 2: Normalize names and data types.
-- - Convert date strings/numeric YYYYMMDD values into ISO dates.
-- - Convert amounts and flags into numeric values.
-- - Remove exact duplicate rows using DISTINCT.
-- - Drop area_business because it is empty in this dataset.
CREATE TABLE invoice_normalized AS
SELECT DISTINCT
    NULLIF(TRIM(business_code), '') AS business_code,
    NULLIF(TRIM(customer_id_raw), '') AS customer_id,
    NULLIF(TRIM(customer_name_raw), '') AS customer_name,

    CASE
        WHEN NULLIF(TRIM(clear_date_raw), '') IS NULL THEN NULL
        ELSE DATE(SUBSTR(TRIM(clear_date_raw), 1, 10))
    END AS clear_date,

    CAST(CAST(NULLIF(TRIM(business_year_raw), '') AS REAL) AS INTEGER) AS business_year,
    PRINTF('%.0f', CAST(NULLIF(TRIM(doc_id_raw), '') AS REAL)) AS doc_id,

    CASE
        WHEN NULLIF(TRIM(posting_date_raw), '') IS NULL THEN NULL
        ELSE DATE(SUBSTR(TRIM(posting_date_raw), 1, 10))
    END AS posting_date,

    CASE
        WHEN NULLIF(TRIM(document_create_date_raw), '') IS NULL THEN NULL
        ELSE
            DATE(
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(document_create_date_raw), '') AS INTEGER)), 1, 4) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(document_create_date_raw), '') AS INTEGER)), 5, 2) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(document_create_date_raw), '') AS INTEGER)), 7, 2)
            )
    END AS document_create_date,

    CASE
        WHEN NULLIF(TRIM(document_create_date_1_raw), '') IS NULL THEN NULL
        ELSE
            DATE(
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(document_create_date_1_raw), '') AS INTEGER)), 1, 4) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(document_create_date_1_raw), '') AS INTEGER)), 5, 2) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(document_create_date_1_raw), '') AS INTEGER)), 7, 2)
            )
    END AS document_create_date_1,

    CASE
        WHEN NULLIF(TRIM(due_date_raw), '') IS NULL THEN NULL
        ELSE
            DATE(
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(due_date_raw), '') AS INTEGER)), 1, 4) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(due_date_raw), '') AS INTEGER)), 5, 2) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(due_date_raw), '') AS INTEGER)), 7, 2)
            )
    END AS due_date,

    NULLIF(TRIM(invoice_currency_raw), '') AS currency,
    NULLIF(TRIM(document_type_raw), '') AS document_type,
    CAST(CAST(NULLIF(TRIM(posting_id_raw), '') AS REAL) AS INTEGER) AS posting_id,
    CAST(NULLIF(TRIM(invoice_amount_raw), '') AS REAL) AS invoice_amount,

    CASE
        WHEN NULLIF(TRIM(baseline_create_date_raw), '') IS NULL THEN NULL
        ELSE
            DATE(
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(baseline_create_date_raw), '') AS INTEGER)), 1, 4) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(baseline_create_date_raw), '') AS INTEGER)), 5, 2) || '-' ||
                SUBSTR(PRINTF('%08d', CAST(NULLIF(TRIM(baseline_create_date_raw), '') AS INTEGER)), 7, 2)
            )
    END AS baseline_create_date,

    NULLIF(TRIM(payment_terms_raw), '') AS payment_terms,
    PRINTF('%.0f', CAST(NULLIF(TRIM(invoice_id_raw), '') AS REAL)) AS invoice_id,
    CAST(CAST(NULLIF(TRIM(is_open_raw), '') AS REAL) AS INTEGER) AS is_open
FROM invoice_raw;

DROP TABLE IF EXISTS invoice_review;

-- Step 3: Mark rows that should be rejected before modeling.
-- This keeps data-quality decisions visible instead of silently deleting rows.
CREATE TABLE invoice_review AS
SELECT
    *,
    CASE
        WHEN invoice_id IS NULL OR invoice_id = '0' THEN 'Missing invoice ID'
        WHEN customer_id IS NULL THEN 'Missing customer'
        WHEN posting_date IS NULL THEN 'Invalid posting date'
        WHEN due_date IS NULL THEN 'Invalid due date'
        WHEN invoice_amount IS NULL OR invoice_amount <= 0 THEN 'Invalid invoice amount'
        WHEN is_open NOT IN (0, 1) THEN 'Invalid open status'
        WHEN is_open = 0 AND clear_date IS NULL THEN 'Closed invoice missing clear date'
        WHEN is_open = 1 AND clear_date IS NOT NULL THEN 'Open invoice has clear date'
        WHEN clear_date IS NOT NULL AND clear_date < posting_date THEN 'Clear date before posting date'
        ELSE NULL
    END AS rejection_reason
FROM invoice_normalized;

DROP TABLE IF EXISTS invoice_clean;

-- Step 4: Keep only valid rows and add target variables.
-- payment_delay_days and is_late are for training/evaluation only;
-- do not use them as model inputs because they depend on clear_date.
CREATE TABLE invoice_clean AS
SELECT
    business_code,
    customer_id,
    customer_name,
    clear_date,
    business_year,
    doc_id,
    posting_date,
    document_create_date,
    document_create_date_1,
    due_date,
    currency,
    document_type,
    posting_id,
    invoice_amount,
    baseline_create_date,
    payment_terms,
    invoice_id,
    is_open,
    CASE
        WHEN clear_date IS NULL THEN NULL
        ELSE CAST(JULIANDAY(clear_date) - JULIANDAY(due_date) AS INTEGER)
    END AS payment_delay_days,
    CASE
        WHEN clear_date IS NULL THEN NULL
        WHEN clear_date > due_date THEN 1
        ELSE 0
    END AS is_late
FROM invoice_review
WHERE rejection_reason IS NULL;

-- Step 5: Add practical indexes for lookups and later feature engineering.
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_clean_invoice_id
ON invoice_clean(invoice_id);

CREATE INDEX IF NOT EXISTS idx_invoice_clean_customer_date
ON invoice_clean(customer_id, posting_date);

CREATE INDEX IF NOT EXISTS idx_invoice_clean_open_date
ON invoice_clean(is_open, posting_date);

DROP VIEW IF EXISTS labeled_invoices;
DROP VIEW IF EXISTS open_invoices;
DROP VIEW IF EXISTS invoice_risk_training_view;

-- Step 6: Create useful views.
-- labeled_invoices are safe for supervised model training because clear_date exists.
CREATE VIEW labeled_invoices AS
SELECT *
FROM invoice_clean
WHERE is_open = 0
  AND clear_date IS NOT NULL;

-- open_invoices look like prediction candidates, but in this Kaggle dataset
-- they are not ERPNext Sales Invoices.
CREATE VIEW open_invoices AS
SELECT *
FROM invoice_clean
WHERE is_open = 1
  AND clear_date IS NULL;

-- Compact view that is closer to the future risk-scoring shape.
CREATE VIEW invoice_risk_training_view AS
SELECT
    customer_id,
    customer_name,
    invoice_id,
    posting_date,
    due_date,
    invoice_amount,
    currency,
    payment_terms,
    is_open,
    payment_delay_days,
    is_late
FROM invoice_clean;

-- Step 7: Print a compact quality report.
.headers on
.mode column

SELECT 'raw_rows' AS metric, COUNT(*) AS value FROM invoice_raw
UNION ALL
SELECT 'normalized_rows', COUNT(*) FROM invoice_normalized
UNION ALL
SELECT 'clean_rows', COUNT(*) FROM invoice_clean
UNION ALL
SELECT 'rejected_rows', COUNT(*) FROM invoice_review WHERE rejection_reason IS NOT NULL
UNION ALL
SELECT 'labeled_paid_rows', COUNT(*) FROM labeled_invoices
UNION ALL
SELECT 'open_invoice_rows', COUNT(*) FROM open_invoices;

SELECT
    COALESCE(rejection_reason, 'Accepted') AS status,
    COUNT(*) AS rows
FROM invoice_review
GROUP BY COALESCE(rejection_reason, 'Accepted')
ORDER BY rows DESC;

SELECT
    currency,
    COUNT(*) AS invoices,
    ROUND(SUM(invoice_amount), 2) AS total_invoice_amount
FROM invoice_clean
GROUP BY currency
ORDER BY invoices DESC;

SELECT
    MIN(posting_date) AS earliest_posting_date,
    MAX(posting_date) AS latest_posting_date,
    ROUND(AVG(payment_delay_days), 2) AS avg_payment_delay_days,
    ROUND(100.0 * AVG(is_late), 2) AS late_payment_rate_percent
FROM labeled_invoices;

-- Step 8: Export the cleaned dataset as CSV.
.headers on
.mode csv
.once "ml/data/dataset_clean.csv"
SELECT *
FROM invoice_clean
ORDER BY posting_date, invoice_id;
