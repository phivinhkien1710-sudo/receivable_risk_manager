# Deployment Guide

For whoever provisions and operates this app — **not for end users** (see
`USER_GUIDE.md` for those). Infra-agnostic on purpose: no host, cloud provider, or
domain is assumed. Check the requirements below against whatever environment gets
chosen.

This package ships **no data.** A fresh install starts empty; loading invoices is a
separate action against your own CSV (see README's "Dataset").

## Infrastructure requirements

- A Frappe/ERPNext **bench**, v15, Python 3.10+.
- **Redis** — a bench requirement regardless, but in production it must be a
  properly managed instance, not something hand-started for a dev session. See
  "The background worker is not optional" below for why this matters more here
  than it looks.
- A **process manager** — `bench setup production` (supervisor + nginx) or
  equivalent. `bench start` in a terminal is a development tool: it dies with the
  session, has no restart-on-crash, and takes the background worker down with it.
- The **`claude` CLI**, reachable *by the machine running the background worker* —
  required for AI Review Runs. Billed via whatever Claude subscription is logged in
  on that host, not a metered API key.

## Install

```bash
bench new-site <your-site>.local
bench get-app receivable_risk_manager <path-or-url-to-this-repo>
bench --site <your-site>.local install-app receivable_risk_manager
bench --site <your-site>.local scheduler enable
```

Or use `./install.sh` for a one-command Docker-based install from scratch.

## The background worker is not optional

This is the single most important operational fact about this app, and it has
already caused a real failure worth learning from.

Both the CSV import and AI Review Runs are **queued to a background worker**, not
executed inline. `Receivables Import Job` sets itself to `Queued`, hands the work
to the queue, and the form tells the user it is running in the background. If no
worker is consuming that queue, the job sits in `Queued` **forever**, looking
healthy, doing nothing.

On the development site this happened 27 times over two months, entirely unnoticed,
because all real work was being driven through `bench execute` (which runs inline
and needs no worker) while every click of the Desk import button silently went
nowhere.

Two defences now exist, and you should understand both:

1. **`hourly_reconcile_import_jobs`** (registered in `hooks.py`) fails any job that
   has sat in `Queued`/`Importing` for over an hour with no live queue entry behind
   it, with an error message explaining why. This depends on the scheduler being
   enabled — if the scheduler is off, this guard is off too.
2. **`AI Review Run`** records its own failure on the document, so a failed AI pass
   is visible rather than silent.

Neither defence makes the work happen. They only stop it from *pretending* to. You
still need a live worker.

Verify you have one:

```bash
ps aux | grep "bench worker"          # should be non-empty
bench --site <your-site>.local doctor # queue and scheduler health
```

## The Claude CLI and PATH

`services/ai_review.py` invokes the `claude` binary as a subprocess. A background
worker is spawned with a **stripped PATH** that does not include Homebrew, `/usr/local`,
or anything from your shell profile — so a CLI that works perfectly in your terminal
can be completely invisible to the process that actually needs it.

This is not hypothetical: the first AI Review Run started from the Desk UI failed
instantly with "CLI not found" while the identical code worked from a console.

`discover_claude_cli()` handles the common cases (PATH, plus the Claude Code VS Code
extension's bundled binary). If it still cannot find it, set an absolute path in
**Risk Settings → AI Review CLI Path**:

```bash
which claude   # then paste that absolute path into Risk Settings
```

## Configuration checklist

- [ ] Scheduler enabled (`bench --site <site> scheduler enable`)
- [ ] Background worker running and supervised
- [ ] `claude` CLI reachable **by the worker**, or an absolute path set in Risk Settings
- [ ] **Risk Settings** reviewed: risk thresholds, scoring weights, `follow_up_days`
- [ ] `ai_min_confidence` reviewed (default 0.7) — below this, Claude's verdict is
      discarded in favour of the rule engine
- [ ] Roles assigned: `Accounts Manager` approves/rejects proposals; `Accounts User`
      works approved actions

## What runs unattended vs. what a human triggers

Deliberate, and worth stating plainly to whoever operates this:

| Runs on a schedule | Started by a human |
|---|---|
| Customer aggregation and risk scoring | AI Review Run (proposing actions) |
| Invoice risk assessment | CSV import |
| Follow-up check (escalating stale approved actions — fully deterministic) | Approving/rejecting any proposal |
| Import job reconciliation | |

**Nothing that decides what to do about a customer fires unattended**, and nothing
is ever sent to a customer by this app at all — it produces proposals for humans.

## Known gaps

Real things found by running this, not hypothetical concerns.

**A pre-existing `sync_jobs` crash on this bench.** `bench migrate` fails at the very
end inside Frappe's own scheduler sync (`croniter` receiving a `None` cron format),
unrelated to this app and present before this work. Schema changes and patches apply
successfully *before* the crash, so migrations do land — but the scheduled-job
registrations may not sync. Verify `Scheduled Job Type` records exist after migrating.

**Scale of an AI review pass.** Each chunk is one CLI call (default 25 invoices).
Reviewing all ~9,700 open assessments is ~390 calls. Use `limit_rows`, or scope to
one import batch, rather than starting an unbounded run casually.

**Historical imports have no batch membership.** Membership is recorded at import
time going forward; imports that predate this feature never recorded which invoices
they touched, and it is not reconstructible. The Batch Workflow menu will appear on
those old jobs and find nothing. Re-import the CSV through a fresh Import Job to get
a real batch (the import is idempotent — it updates rather than duplicates).

**No bulk approve.** Proposals are approved one at a time, deliberately — but at
volume that is a genuine bottleneck. Flagging it rather than quietly building it.

## Verifying a fresh install

```bash
bench new-site rrm-verify.local
bench --site rrm-verify.local install-app receivable_risk_manager
bench --site rrm-verify.local run-tests --app receivable_risk_manager
```

Then follow README's Getting Started literally, step by step, against that site —
the point is to catch drift between what the docs claim and what the code needs
before it matters. Import a small CSV **through the Desk UI, not `bench execute`**,
so you actually exercise the queued path and prove the worker is alive.
