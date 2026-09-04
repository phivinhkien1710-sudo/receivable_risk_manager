# Using the Receivables Risk Manager

This guide is for the credit-control team: importing invoices, reviewing what the
system proposes, and deciding what actually happens. No technical knowledge needed —
everything here is clicking buttons and filling in forms.

If nobody has set this up yet and you have no web address to log into, that is a job
for whoever runs your systems — point them at `docs/DEPLOYMENT.md`.

## The one-sentence version

The system scores every overdue invoice, Claude reviews them and proposes what to do,
and **nothing happens until a human approves it.**

## Your daily screen

Open **Collection Action Queue** and filter **Status = Proposed**. That is your to-do
list: everything the system thinks needs attention and nobody has decided on yet.

Everything else — the dashboard, Customer Risk Overview, Invoice Collection Priority
— is for looking into a question. The queue is where the work is.

## Step 1 — Import invoices

Search for **Receivables Import Job**, click **New**, attach your CSV, set the
**As Of Date**, and save. Click **Validate**, check the row counts and any errors,
then **Start Import**.

The import runs in the background. The form tells you when it finishes.

**If it sits on "Queued" for more than a few minutes, something is wrong** — that
means no background worker is running, which is a technical problem, not something
you can fix from this screen. Flag it. (The system will eventually mark such a job
`Failed` on its own with an explanation, rather than leaving you waiting forever.)

Importing the same file twice is safe: existing invoices are updated, not duplicated.

## Step 2 — Run the AI review on that batch

Open the completed import job. In the **Batch Workflow** menu:

**Batch Workflow → Run AI Review**

This opens a new AI Review Run with your batch already filled in. Save it, then click
**Start Review**.

You can leave **Limit Rows** blank to review everything in the batch, or set a number
to try a small slice first. Reviewing a few thousand invoices takes a while — it
runs in the background, so you can close the page and come back.

### What Claude actually does here

It reads each overdue invoice **plus that customer's payment history** and proposes
what to do about it — send a reminder, follow up personally, escalate to collections,
or leave it alone.

The value is the history. The rule engine only sees one invoice's age. Claude can see
that a customer who *always* pays 42 days late being 40 days late is behaving
normally, while a customer who always pays on time being 40 days late is a real
signal — and that a small invoice matters more when that customer owes you a million
across 66 other invoices.

When the run finishes it tells you exactly what it did: how many it reviewed, how many
actions it proposed, and — most usefully — **how many it disagreed with the rules on.**

## Step 3 — Review the disagreements first

**Batch Workflow → Disagreements Only**

These are the invoices where Claude and the rule engine reached different conclusions.
Out of hundreds reviewed, this is usually a handful — and it is where your judgement
is genuinely needed rather than rubber-stamping.

Each row shows **Rule Said**, **AI Said**, **AI Confidence**, and **AI Reasoning** side
by side, so you can see the disagreement and the argument for it without opening
anything.

**One thing to understand about safety**: Claude can propose something *more* serious
than the rules and that is what you will see proposed. But if Claude argues for
something *less* serious — "leave this one alone" — the system **keeps the rule's
recommendation anyway** and just records Claude's argument for you to consider. The AI
is never allowed to quietly talk the system out of chasing a debt. Worst case, you
spend ten seconds rejecting a proposal you disagree with.

## Step 4 — Approve or reject

Open any **Proposed** action. You will see the proposal, the reasoning, and the
invoice it relates to. Then:

- **Approve** — it becomes a live action your team works on
- **Reject** — it goes away, recorded as rejected

Only an **Accounts Manager** can approve or reject. That is deliberate.

## Step 5 — Work the approved actions

Approved actions sit at **Open**. As you work them:

- **Mark as Contacted** — you have reached out
- **Promised to Pay** — they have committed to a date
- **Resolve** — done, or the invoice was paid

Any Accounts User can do these. Escalating to a higher severity needs a manager.

## What happens on its own

- Risk scores refresh daily as invoices age.
- If an approved action sits unresolved past the follow-up window (3 days by default),
  the system notices and **proposes an escalation** — which comes back to you for
  approval, exactly like any other proposal. It never escalates on its own authority.
- Actions on invoices that get paid are resolved automatically.

## Things worth knowing

**Nothing is ever sent to a customer by this app.** It produces proposals and
prioritised lists. Every actual contact is made by a person.

**Low-risk invoices get no proposal**, by design. If you want to see everything
regardless, use Invoice Collection Priority instead of the queue.

**If a number looks wrong**, check the **Risk Audit Log** for that invoice — it
records every scoring decision, proposal, and AI verdict with a reason, so you can
see why the system concluded what it did.

## If something looks broken

A missing button, a page that will not load, a job stuck on "Queued", or an AI review
that fails immediately — those are for whoever set this up technically. Tell them what
page you were on and what you expected. If an AI Review Run failed, its **Error
Summary** field usually says exactly what went wrong; include that.
