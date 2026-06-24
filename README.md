# Receivables Risk Manager

A Frappe/ERPNext app that helps SMEs identify risky customers, prioritize overdue invoices, and generate collection actions using rule-based receivables risk scoring.

This project was built as a SWE portfolio project for a potential NUS FinTech Lab software engineering role. It focuses on practical FinTech/SME credit operations: turning invoice-payment history into customer risk profiles, open-invoice risk assessments, and operational collection queues.

## Business Problem

Small and medium-sized enterprises often manage receivables reactively. They may know which invoices are overdue, but not which customers are becoming risky, which open invoices deserve immediate attention, or what collection action should happen next.

Receivables Risk Manager addresses this by:

- aggregating historical invoice behavior by customer;
- calculating customer risk from payment delay, late-payment rate, and open exposure;
- assessing open invoice risk using customer risk, overdue days, and invoice amount;
- generating collection actions for medium/high-risk invoices;
- exposing risk and collection queues through Frappe Script Reports.

## MVP Architecture

The MVP is dataset-driven and uses custom DocTypes instead of importing into ERPNext `Sales Invoice`.

```text
dataset_clean.csv
    ↓
Receivables Invoice
    ↓
Receivables Customer aggregation
    ↓
Customer Risk Scoring
    ↓
Invoice Risk Assessment
    ↓
Collection Action
    ↓
Reports
    ↓
Daily Scheduled Recalculation
```

### Main DocTypes

- `Receivables Invoice` — normalized invoice rows imported from the cleaned CSV dataset.
- `Receivables Customer` — customer-level aggregates and risk fields.
- `Risk Settings` — configurable risk thresholds/weights for future settings-driven scoring.
- `Invoice Risk Assessment` — calculated risk state for each open invoice.
- `Collection Action` — follow-up action generated from medium/high-risk invoice assessments.

### Main Services

```text
receivable_risk_manager/imports/
  invoice_imports.py              # CSV import

receivable_risk_manager/services/
  customer_aggregation.py         # invoice → customer aggregates
  risk_scoring.py                 # pure Python scoring functions
  customer_risk.py                # persists customer risk fields
  invoice_risk.py                 # creates/updates invoice risk assessments
  collection_actions.py           # generates collection actions
  data_quality.py                 # read-only data quality checks

receivable_risk_manager/tasks.py  # full scheduled recalculation pipeline
```

Actual package name:

```text
receivable_risk_manager
```

Product name:

```text
Receivables Risk Manager
```

## Key Features

- CSV import for a public receivables invoice dataset.
- Custom normalized DocTypes for analytical invoice-payment data.
- Customer aggregation by `customer_id`.
- Rule-based customer risk scoring.
- Risk confidence for limited payment history.
- Open invoice risk assessment.
- Collection action generation.
- Duplicate-safe collection action creation.
- Stale-record handling when invoices close.
- Script Reports:
  - `Customer Risk Overview`
  - `Open Invoice Risk List`
  - `Collection Action Queue`
- Daily scheduled recalculation pipeline.
- Read-only data quality checks.
- Unit tests for pure scoring functions.

## Technical Design Decisions

### Why custom DocTypes instead of ERPNext Sales Invoice?

The source dataset is analytical invoice-payment data, not a full ERP accounting export. ERPNext `Sales Invoice` requires accounting context such as company, items, accounts, taxes, posting rules, and ledger behavior. Importing directly into ERPNext accounting documents would add significant setup complexity and could distract from the core risk-scoring objective.

For the MVP, the app uses custom DocTypes:

- faster to build and demo;
- safer for public historical datasets;
- focused on risk analytics and collection workflow;
- leaves ERPNext accounting integration as a future improvement.

### Why rule-based scoring instead of machine learning?

The goal is to build a transparent and operationally useful MVP. Rule-based scoring is:

- easier to explain to business users;
- easier to test;
- deterministic;
- suitable for a portfolio project demonstrating backend design, data modeling, batch processing, and Frappe conventions.

Machine learning can be added later once the baseline workflow is reliable.

## Setup

### Prerequisites

- Frappe Bench
- Frappe v15 / ERPNext v15 development environment
- A site, for example:

```bash
staging.local
```

### Install App

From your bench directory:

```bash
cd /path/to/frappe-bench
bench get-app https://github.com/<your-username>/receivable_risk_manager.git
bench --site staging.local install-app receivable_risk_manager
bench --site staging.local migrate
```

If the app already exists locally:

```bash
cd /path/to/frappe-bench
bench --site staging.local migrate
bench --site staging.local clear-cache
```

## Data Import

The dataset file is intentionally not committed. Local data files should live under:

```text
apps/receivable_risk_manager/ml/data/
```

That folder is ignored by Git.

Example import command:

```bash
cd /path/to/frappe-bench
bench --site staging.local execute receivable_risk_manager.imports.invoice_imports.import_dataset \
  --kwargs "{'csv_path': 'apps/receivable_risk_manager/ml/data/dataset_clean.csv'}"
```

Optional limited import for smoke testing:

```bash
bench --site staging.local execute receivable_risk_manager.imports.invoice_imports.import_dataset \
  --kwargs "{'csv_path': 'apps/receivable_risk_manager/ml/data/dataset_clean.csv', 'limit': 1000}"
```

## Recalculation Pipeline

Run the full recalculation pipeline manually:

```bash
bench --site staging.local execute receivable_risk_manager.tasks.run_full_recalculation
```

This runs:

1. customer aggregation;
2. customer risk scoring;
3. invoice risk assessment;
4. collection action generation.

Possible pipeline statuses:

- `success` — all major steps completed with no row-level errors.
- `completed_with_errors` — all major steps completed, but one or more child steps reported row-level errors.
- `failed` — a major exception stopped the pipeline.

Run only the scheduled task target:

```bash
bench --site staging.local execute receivable_risk_manager.tasks.daily_recalculate_receivables_risk
```

Check that the scheduler hook is registered:

```bash
bench --site staging.local execute frappe.get_hooks --args "['scheduler_events']"
```

## Data Quality Check

Run the read-only data quality check:

```bash
bench --site staging.local execute receivable_risk_manager.services.data_quality.validate_receivables_data_quality
```

The summary includes:

- total invoices;
- missing customer IDs;
- missing invoice IDs;
- missing due dates;
- open/closed invoice counts;
- unique customer count;
- invalid open flags;
- negative invoice amounts;
- inconsistent clear-date/open-status cases.

## Tests

The scoring functions are pure Python and can be tested without a Frappe database.

From the app directory:

```bash
cd /path/to/frappe-bench/apps/receivable_risk_manager
python3 -m unittest receivable_risk_manager.tests.test_risk_scoring
```

Expected result:

```text
Ran 13 tests

OK
```

## Demo Flow

Suggested demo sequence:

1. Import `dataset_clean.csv` into `Receivables Invoice`.
2. Run the full recalculation pipeline.
3. Open `Customer Risk Overview`.
   - Show high-risk customers.
   - Explain `risk_score`, `risk_level`, and `risk_confidence`.
4. Open `Open Invoice Risk List`.
   - Show Medium/High-risk open invoices.
   - Explain overdue days, customer risk contribution, and suggested actions.
5. Open `Collection Action Queue`.
   - Show generated collection actions sorted by due date and risk score.
6. Run the data quality check.
   - Show that the import is validated before analytics are trusted.
7. Briefly show the scheduler hook.
   - Explain that the risk pipeline can run daily.

## Reports

### Customer Risk Overview

Source: `Receivables Customer`

Used to review customer-level exposure and payment behavior:

- total invoices;
- open invoice count;
- open amount;
- average payment delay;
- late payment rate;
- risk score;
- risk level;
- risk confidence;
- risk explanation.

### Open Invoice Risk List

Source: `Invoice Risk Assessment`

Used to prioritize risky open invoices:

- days overdue;
- invoice amount;
- customer risk score;
- invoice risk score;
- suggested action;
- explanation.

### Collection Action Queue

Source: `Collection Action`

Used as an operational queue for follow-up:

- action type;
- priority;
- status;
- due date;
- originating risk score;
- notes.

## Project Structure

```text
receivable_risk_manager/
  receivable_risk_manager/
    hooks.py
    tasks.py

    imports/
      invoice_imports.py

    services/
      customer_aggregation.py
      customer_risk.py
      invoice_risk.py
      collection_actions.py
      risk_scoring.py
      data_quality.py

    tests/
      test_risk_scoring.py

    receivable_risk_manager/
      doctype/
        receivables_invoice/
        receivables_customer/
        risk_settings/
        invoice_risk_assessment/
        collection_action/

      report/
        customer_risk_overview/
        open_invoice_risk_list/
        collection_action_queue/
```

## Future Improvements

- Optional ERPNext integration:
  - map `Receivables Customer` to ERPNext `Customer`;
  - map `Receivables Invoice` to ERPNext `Sales Invoice`;
  - add sales-order warnings based on customer risk.
- Settings-driven scoring using `Risk Settings`.
- Additional dashboard charts for risk distribution and open exposure.
- More advanced collection workflow with assignment rules and SLA aging.
- Better import UI for uploading CSV files from Desk.
- Background job queue support for large imports.
- Machine learning model for payment-date prediction after the rule-based baseline is stable.
- Role-based permission refinement for finance, sales, and management users.

## License

MIT
