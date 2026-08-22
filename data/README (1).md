# Dataset: DunningTrail — Synthetic B2B Receivables

## invoices.csv (agent-visible)
75 overdue B2B invoices, ~INR 2.75 Cr total outstanding.

| column | meaning |
|---|---|
| invoice_id | unique invoice identifier |
| customer_id | customer identifier (some customers repeat across invoices) |
| customer_name | synthetic company name |
| industry | customer's industry |
| invoice_amount | outstanding amount (INR) |
| invoice_date / due_date | issue and due dates |
| days_overdue | days past due_date, relative to simulation "today" (2026-03-01) |
| payment_history_score | 0-1, customer's historical reliability (beta-distributed) |
| risk_segment | low/medium/high, derived from history score + days overdue |
| prior_contact_count | starts at 0, agent must update this as it acts |
| contact_email, preferred_channel, language_pref | contact metadata (language_pref includes Hinglish, for the Hinglish voice recovery direction) |
| status | starts "overdue"; agent updates as it progresses cases |

## ground_truth_HIDDEN.csv (simulation engine only — agent must NOT read this)
For each invoice x each of 5 possible actions
(gentle_reminder, firm_reminder, phone_call, payment_plan_offer, escalate_collections):
- `pay_prob` — probability customer pays in full after this action
- `promise_prob` — probability customer promises to pay by a future date
- `partial_pay_prob` — probability of partial payment
- `ignore_prob` — probability of no response
- `annoyance_penalty` — how much this action reduces future responsiveness
  if the customer is contacted again (escalate_collections damages the
  relationship most; payment_plan_offer damages it least)

This file is the simulation engine's internal model of "how would this
customer actually respond." The agent's decision logic never sees it — it
only sees `invoices.csv` and the outcomes of actions it has already taken.
This mirrors the same train/test separation discipline as the reconciliation
project: policy quality is judged against a hidden model, not by peeking.

## Design intent
- The agent must choose actions under uncertainty, respecting compliance
  rules (e.g., must attempt lower-intensity actions before escalating) and
  stopping rules (max contact attempts, cooldown periods, stop once paid/
  promised/written-off).
- Money recovered is measured by running the agent's chosen actions through
  the hidden response model and comparing total recovered amount against a
  baseline policy (e.g., single-tier "email everyone once").

## Regenerating
`python3 scripts/generate_data.py` (seeded, reproducible)
