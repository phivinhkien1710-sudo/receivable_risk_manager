# Demo Voiceover Script

Paired with `DEMO_SCRIPT.md`. Target runtime **4:00–4:30**. Word counts assume
~145 words/minute — comfortable, unhurried delivery.

Delivery notes:
- Read the disagreement quotes **verbatim from screen**. Real model output is
  the most persuasive thing in the demo; don't paraphrase it.
- The one line that must land clearly is the guardrail in Section 6. If a
  judge remembers one sentence, it should be that one.
- Section 4 covers the AI run's ~60–90s execution. If you cut or timelapse
  that footage, trim this section proportionally.

---

## 1. Cold open — the problem
**(~20s, 45 words)**

> Every one of these is an overdue invoice. Four hundred and ninety-eight of
> them, and this is the small demo set — the full dataset is forty-eight
> thousand. No credit-control team reads through this. They need to know which
> ones actually deserve their attention today.

---

## 2. Import
**(~25s, 60 words)**

> It starts with an import. A CSV of invoices comes in, gets validated, and
> lands as structured records. What matters here is that the import is
> batch-tracked — every invoice it brings in is tagged as belonging to this
> specific batch. That's what lets every later stage be scoped to just today's
> import, instead of operating on the entire database every time.

---

## 3. Launching the agent
**(~30s, 70 words)**

> From the completed import, there's a Batch Workflow menu. This is the spine
> of the whole thing — each entry runs one stage against this batch. I'm
> starting an AI Review Run.
>
> Notice this is deliberate. A human scopes it and starts it. And the
> confirmation is explicit: nothing gets sent to any customer, and every single
> thing the agent proposes still needs approval before it means anything.

---

## 4. What the agent sees
**(~45s, 110 words — covers the run's execution time)**

> While that runs, here's what's actually happening.
>
> Underneath this, there's a deterministic rule engine that already scored
> every invoice — days overdue, risk level, a number. That runs daily, costs
> nothing, and never misses anything.
>
> The agent isn't replacing it. Every invoice it reviews arrives with the rule
> engine's own recommendation attached. It's not asked "what should happen
> here." It's asked: here's what the rules already decided — does the fuller
> picture change that?
>
> And the fuller picture is the part the rules structurally cannot see. Rules
> look at one invoice in isolation. The agent also sees how this customer has
> paid historically, and how much they owe across everything else.

---

## 5. Results
**(~35s, 85 words)**

> Twenty invoices reviewed, in about a minute.
>
> And look at how this reports itself. It proposed action on twenty — but it
> only created five new records, because fifteen of those invoices already had
> an action from an earlier run. Those are deliberately separate numbers. An
> earlier version of this reported only the first one, which meant it was
> effectively overstating its own output.
>
> But the number that matters is this one. It disagreed with the rule engine on
> nine of twenty.

---

## 6. The disagreements — the core
**(~70s, 165 words)**

> This is the actual product. Not the agreements — the disagreements.
>
> Here's the rule engine's decision, the agent's decision, its confidence, and
> its reasoning, side by side.
>
> Here it's pushing *harder* than the rules. Reading its own words: *"COSTCO
> normally pays only 4.1 days late but is 74 days overdue — a dramatic
> departure from pattern. Customer has $2.29 million open exposure."* The rules
> saw one late invoice. The agent saw a reliable customer suddenly behaving
> abnormally, with real money behind it.
>
> And here it's pushing the other way — arguing for a gentler follow-up instead
> of formal collections, because this customer is normally reliable and this
> looks like a one-off anomaly worth investigating rather than escalating.
>
> Now — the important part.
>
> The agent can escalate beyond the rules on its own authority. But when it
> argues for something *less* severe, the rule's action stays in force. The
> disagreement gets recorded for a human to judge. The AI is never allowed to
> quietly talk this system out of chasing a debt.

---

## 7. Human in the loop
**(~25s, 60 words)**

> Every proposal lands here, waiting. A human with the right role approves or
> rejects it. Approve, and it becomes live work for the collections team.
>
> Until that click, the agent's entire output is a suggestion. It has no
> ability to act on a customer by itself — the app doesn't even have a path to
> send anything.

---

## 8. Audit trail
**(~20s, 50 words)**

> And everything is on the record. Every score, every agent verdict, every
> disagreement, tagged by source. Months from now you can reconstruct exactly
> why this system concluded anything — which matters a lot when the thing
> making judgment calls is a language model.

---

## 9. Close
**(~25s, 60 words)**

> So: the deterministic parts run unattended and never miss anything. The
> judgment runs only when a human asks for it. And nothing reaches a customer
> without a person approving it first.
>
> The agent's job isn't to automate the decision. It's to find the handful of
> cases, out of hundreds, where the obvious answer is wrong.

---

## Total: ~4:15

## Alternate 90-second cut

If you need a short version, keep only:

1. **Problem** (15s) — 498 invoices, nobody reads these.
2. **Launch** (15s) — human scopes and starts the agent; nothing sends without approval.
3. **Results** (20s) — 20 reviewed, disagreed on 9. Those 9 are the product.
4. **One disagreement** (25s) — read the COSTCO quote verbatim from screen.
5. **Guardrail** (15s) — can escalate on its own authority, can never de-escalate silently.
