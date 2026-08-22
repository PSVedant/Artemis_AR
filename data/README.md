# Dataset: Artemis_AR — Synthetic B2B Receivables (v2)

## customers.csv (agent-visible)
40 synthetic customers.

| column | meaning |
|---|---|
| customer_id | unique customer identifier |
| customer_name | synthetic company name |
| industry | customer's industry |
| annual_revenue_inr | synthetic annual revenue, drives relationship tier |
| relationship_tier | VIP / Standard / New, derived from revenue |
| importance_score | 0-1, visible to the agent; higher = more relationship-sensitive |
| payment_history_score | 0-1, customer's historical reliability |
| preferred_channel, language_pref | contact metadata (Hinglish supported) |

## invoices.csv (agent-visible)
75 overdue invoices, FK'd to customers.csv via customer_id.

| column | meaning |
|---|---|
| invoice_id | unique invoice identifier |
| customer_id | FK to customers.csv |
| invoice_amount | outstanding amount (INR) |
| invoice_date / due_date | issue and due dates |
| days_overdue | days past due, relative to simulation "today" (2026-03-01) |
| risk_segment | low/medium/high, derived from customer history + days overdue |
| prior_contact_count | starts at 0, agent updates during simulation |
| status | starts "overdue"; agent updates as it progresses cases |

## ground_truth_HIDDEN.csv (simulation engine only — agent must NOT read this)
Per invoice x per action (gentle_reminder, firm_reminder, phone_call,
payment_plan_offer, escalate_collections):
- `pay_prob`, `promise_prob`, `partial_pay_prob`, `ignore_prob`
- `annoyance_penalty` — now scaled by the customer's importance_score.
  Escalating on a VIP customer costs roughly 2x the relationship damage of
  escalating on a low-importance one. The agent never sees this number
  directly — it only sees importance_score and must learn to be more
  conservative with high-importance customers through policy design, not
  by peeking at the hidden penalty.

## Design intent
Same train/test separation discipline as before: policy quality is judged
by running chosen actions through this hidden model and comparing recovered
amount + relationship damage against a baseline policy that ignores
customer importance. A policy that escalates VIPs as readily as anyone
else should score worse on relationship-damage even if its raw recovery
number looks similar — that's the point of this dataset revision.

## Regenerating
`python3 scripts/generate_data.py` (seeded, reproducible)
