# Screenshot / Recording Checklist

Use this as the click-by-click path for portfolio screenshots or a demo
recording. It follows the same order as the README's "Demo Workflow" section.
The current `staging.local` site already has the full dataset imported and the
recalculation pipeline run (48,833 invoices / 1,424 customers / 22 high-risk
customers / 9,681 invoice risk assessments / 4,467 collection actions), so you
can capture these now without re-importing anything.

If you do want a clean-slate recording, reset first with
`scripts/demo_setup.sh` (see README "Quick Demo Setup").

## Capture order

1. **Receivables Import Job** (only if showing the import flow)
   - New job → attach `dataset_clean.csv` → Save → `Validate` → show the
     validation summary (total/valid/invalid rows) → `Import`.
   - What it proves: finance users can import without a terminal.

2. **Receivables Invoice list**
   - Show the normalized invoice rows imported from the CSV.

3. **Receivables Customer list**
   - Show customer-level aggregates: total invoices, open exposure, risk
     score/level columns.

4. **Receivables Risk Dashboard** (`Report` → Receivables Risk Dashboard)
   - Capture the KPI cards first (total customers, high-risk customers, open
     exposure, risky open invoices, collection workload).
   - Switch the chart metric at least twice on camera if recording video:
     outstanding amount by risk level → aging bucket distribution → collection
     actions by status.
   - Scroll to the Top Risky Customers table.

5. **Customer Risk Overview** report
   - Sort/filter to High risk level.
   - Point out `risk_score`, `risk_level`, `risk_confidence`, and the
     explanation column — this is the "explainability" story.

6. **Invoice Collection Priority** report
   - Filter to Medium/High risk open invoices.
   - Point out overdue days, customer risk contribution, and suggested action.

7. **Collection Action Queue** report
   - Sort by due date, then by risk score.
   - Show a couple of different action types/priorities.

8. **Terminal: data quality + scheduler check** (optional, for a technical
   audience)
   ```bash
   bench --site staging.local execute receivable_risk_manager.services.data_quality.validate_receivables_data_quality
   bench --site staging.local execute frappe.get_hooks --args "['scheduler_events']"
   ```

## Notes for GitHub screenshots (static images)

- Crop to the report/dashboard body; exclude the browser chrome and Desk
  sidebar noise where possible for a tighter image.
- Keep filenames consistent with what the README already references under
  `screenshots/` (e.g. `receivables-risk-dashboard.png` is still a placeholder
  — this is the one screenshot still missing).

## Notes for a demo video

- Narrate the pipeline story in order: import → aggregate → score → assess →
  act → report. That mirrors the architecture diagram in the README and gives
  the recording a clear narrative arc instead of just clicking through pages.
- Keep it under ~90 seconds — reviewers skim.
