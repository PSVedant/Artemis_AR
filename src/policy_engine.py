"""
Policy engine for Artemis_AR.

Given an invoice's current state (+ its customer's attributes), decides the
next action: wait, or one of the 5 contact actions. Enforces:
  - cooldown between contacts
  - ordering constraints (can't escalate straight away)
  - the escalate_collections gate (payment plan tried first, OR severity threshold)
  - human-in-the-loop approval requirement for escalate_collections on
    important customers
  - stopping rules (max attempts, terminal statuses)

This module makes NO network/LLM calls and reads NO hidden ground-truth
data. It is a pure decision function: state in, action out, with a reason
string for the audit trail.
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "policy.json"
with open(CONFIG_PATH) as f:
    POLICY = json.load(f)


@dataclass
class InvoiceState:
    invoice_id: str
    customer_id: str
    days_overdue: int
    risk_segment: str
    importance_score: float
    status: str = "overdue"
    prior_contact_count: int = 0
    last_contact_date: Optional[date] = None
    action_history: list = field(default_factory=list)  # list of (action, outcome)
    original_amount: float = 0.0
    remaining_amount: float = 0.0
    promise_date: Optional[date] = None
    fatigue: float = 0.0  # cumulative annoyance, reduces future responsiveness


@dataclass
class Decision:
    invoice_id: str
    action: str
    reason: str
    requires_human_approval: bool = False


def _last_two_ignored(state: InvoiceState) -> bool:
    if len(state.action_history) < 2:
        return False
    last_two = state.action_history[-2:]
    return all(outcome == "ignore" for _, outcome in last_two)


def _highest_action_tier_used(state: InvoiceState) -> str:
    order = POLICY["action_intensity_order"]
    if not state.action_history:
        return "wait"
    used = [a for a, _ in state.action_history]
    return max(used, key=lambda a: order.index(a))


def decide_next_action(state: InvoiceState, today: date) -> Decision:
    # 1. Stopping rules first -- terminal states never get a new action
    if state.status in POLICY["stopping_statuses"]:
        return Decision(state.invoice_id, "wait",
                         f"Invoice status '{state.status}' is terminal -- no further action.")

    if state.prior_contact_count >= POLICY["max_contact_attempts"]["value"]:
        state.status = "exhausted"
        return Decision(state.invoice_id, "wait",
                         f"Max contact attempts ({POLICY['max_contact_attempts']['value']}) reached -- "
                         f"moved to 'exhausted' for manual review.")

    # 2. Cooldown check
    cooldown = POLICY["cooldown_days"]["value"]
    if state.last_contact_date is not None:
        days_since_contact = (today - state.last_contact_date).days
        if days_since_contact < cooldown:
            return Decision(state.invoice_id, "wait",
                             f"Cooldown active -- last contacted {days_since_contact}d ago, "
                             f"minimum is {cooldown}d.")

    # 3. First-ever contact -> start gentle unless already severely overdue
    if state.prior_contact_count == 0:
        if state.days_overdue > 45:
            return Decision(state.invoice_id, "firm_reminder",
                             "First contact, but invoice already 45+ days overdue -- starting at firm tier.")
        return Decision(state.invoice_id, "gentle_reminder",
                         "First contact -- starting at gentle tier per standard ladder.")

    # 4. Forced tier jump if last two actions were both ignored
    order = POLICY["action_intensity_order"]
    current_tier = _highest_action_tier_used(state)
    current_idx = order.index(current_tier)

    if _last_two_ignored(state):
        next_idx = min(current_idx + 2, len(order) - 1)  # jump at least one extra tier
    else:
        next_idx = min(current_idx + 1, len(order) - 1)

    candidate_action = order[next_idx]

    # 5. Escalation gate for escalate_collections
    if candidate_action == "escalate_collections":
        gate = POLICY["escalate_collections_gate"]
        payment_plan_tried = any(a == "payment_plan_offer" for a, _ in state.action_history)
        severity_ok = (state.days_overdue >= gate["OR_min_days_overdue"] and
                       state.prior_contact_count >= gate["OR_min_prior_contacts"])

        if not (payment_plan_tried or severity_ok):
            # not eligible yet -- fall back to payment_plan_offer instead
            candidate_action = "payment_plan_offer"
            reason = ("Escalation gate not met (no payment plan offered yet, and severity "
                       f"threshold [{gate['OR_min_days_overdue']}d overdue + "
                       f"{gate['OR_min_prior_contacts']} contacts] not reached) -- "
                       "offering payment plan first.")
            return Decision(state.invoice_id, candidate_action, reason)

        # gate passed -- check human approval requirement
        approval_policy = POLICY["human_approval_policy"]
        needs_approval = state.importance_score >= approval_policy["always_require_manual_review_if_importance_score_at_or_above"]

        reason = "Escalation gate satisfied."
        if needs_approval:
            reason += (f" Customer importance_score={state.importance_score} >= threshold -- "
                       "human approval required before this fires.")
        else:
            reason += f" Customer importance_score={state.importance_score} below threshold -- auto-approved."

        return Decision(state.invoice_id, candidate_action, reason, requires_human_approval=needs_approval)

    return Decision(state.invoice_id, candidate_action,
                     f"Escalating from '{current_tier}' to '{candidate_action}' per standard ladder.")


if __name__ == "__main__":
    # quick smoke test
    from datetime import date as d
    s1 = InvoiceState("INV00001", "CUST0001", days_overdue=71, risk_segment="high", importance_score=0.68)
    decision = decide_next_action(s1, today=d(2026, 3, 1))
    print(decision)

    s2 = InvoiceState("INV00002", "CUST0002", days_overdue=23, risk_segment="medium", importance_score=0.15,
                       prior_contact_count=1, last_contact_date=d(2026, 2, 20),
                       action_history=[("gentle_reminder", "ignore")])
    decision2 = decide_next_action(s2, today=d(2026, 3, 1))
    print(decision2)
