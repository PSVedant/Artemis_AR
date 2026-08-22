"""
Baseline policy for Artemis_AR — the naive comparison point.

Same action set, same cooldown, same max-attempts cap as the smart policy
(src/policy_engine.py), so the comparison is fair. But this baseline:
  - ignores customer importance_score entirely
  - has no escalation gate (jumps straight up the ladder regardless of
    whether a payment plan was offered, or how severe the invoice is)
  - never requires human approval before escalate_collections
  - always starts at gentle_reminder regardless of how overdue the invoice
    already is

This represents what a naive fixed-schedule dunning process looks like --
the kind of system many companies actually run today. The comparison in
Day 4's run is: how much money and relationship-goodwill does the smarter
policy save relative to this.
"""

import json
from pathlib import Path

from src.policy_engine import InvoiceState, Decision, POLICY

BASELINE_LADDER = ["gentle_reminder", "firm_reminder", "phone_call",
                    "payment_plan_offer", "escalate_collections"]


def decide_next_action_baseline(state: InvoiceState, today, policy: dict = None) -> Decision:
    policy = policy or POLICY
    if state.status in policy["stopping_statuses"]:
        return Decision(state.invoice_id, "wait", "Terminal status -- no action.")

    if state.prior_contact_count >= policy["max_contact_attempts"]["value"]:
        state.status = "exhausted"
        return Decision(state.invoice_id, "wait", "Max attempts reached -- exhausted.")

    cooldown = policy["cooldown_days"]["value"]
    if state.last_contact_date is not None:
        days_since = (today - state.last_contact_date).days
        if days_since < cooldown:
            return Decision(state.invoice_id, "wait", f"Cooldown active ({days_since}d since contact).")

    if state.prior_contact_count == 0:
        return Decision(state.invoice_id, "gentle_reminder",
                         "Baseline: always starts gentle regardless of severity.")

    idx = min(state.prior_contact_count, len(BASELINE_LADDER) - 1)
    action = BASELINE_LADDER[idx]
    return Decision(state.invoice_id, action,
                     f"Baseline: fixed ladder step {idx+1}, no gate, no importance check.",
                     requires_human_approval=False)
