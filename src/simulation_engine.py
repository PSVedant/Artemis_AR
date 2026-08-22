"""
Simulation engine for Artemis_AR.

This is the ONLY module allowed to read ground_truth_HIDDEN.csv. The policy
engine (src/policy_engine.py) never sees it -- it only sees InvoiceState,
which is built from the visible invoices.csv / customers.csv.

Each simulated day:
  1. Resolve any promises whose promise_date has arrived (paid or broken).
  2. For every non-terminal invoice, ask the policy engine for the next
     action.
  3. If the action isn't "wait", sample an outcome from the hidden
     response model (adjusted for accumulated fatigue), apply it to state,
     and log an audit trail entry.

Produces a run summary: total recovered, per-action breakdown, exceptions,
and the full audit trail -- this is what "measured money recovered ...
with an audit trail" actually means for this project.
"""

import random
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.policy_engine import InvoiceState, decide_next_action, POLICY

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SIM_START_DATE = date(2026, 3, 1)
SIM_DAYS = 40  # simulate ~40 days of dunning activity

random.seed(11)  # reproducible simulation runs


def load_states():
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    invoices = pd.read_csv(DATA_DIR / "invoices.csv")
    customers_by_id = customers.set_index("customer_id").to_dict("index")

    states = {}
    for _, row in invoices.iterrows():
        cust = customers_by_id[row["customer_id"]]
        states[row["invoice_id"]] = InvoiceState(
            invoice_id=row["invoice_id"],
            customer_id=row["customer_id"],
            days_overdue=int(row["days_overdue"]),
            risk_segment=row["risk_segment"],
            importance_score=float(cust["importance_score"]),
            status="overdue",
            original_amount=float(row["invoice_amount"]),
            remaining_amount=float(row["invoice_amount"]),
        )
    return states, customers_by_id


def load_hidden_response_model():
    df = pd.read_csv(DATA_DIR / "ground_truth_HIDDEN.csv")
    # index by (invoice_id, action) for fast lookup
    return {(row["invoice_id"], row["action"]): row for _, row in df.iterrows()}


def sample_outcome(state: InvoiceState, action: str, response_model: dict) -> str:
    """Sample pay / promise / partial / ignore, adjusted for fatigue."""
    key = (state.invoice_id, action)
    row = response_model[key]

    fatigue_discount = max(0.0, 1 - state.fatigue)
    pay_p = row["pay_prob"] * fatigue_discount
    promise_p = row["promise_prob"] * fatigue_discount
    partial_p = row["partial_pay_prob"] * fatigue_discount
    ignore_p = max(0.0, 1 - pay_p - promise_p - partial_p)

    r = random.random()
    if r < pay_p:
        outcome = "pay"
    elif r < pay_p + promise_p:
        outcome = "promise"
    elif r < pay_p + promise_p + partial_p:
        outcome = "partial"
    else:
        outcome = "ignore"

    # update fatigue regardless of outcome -- being contacted is what tires
    # the customer out, not just being ignored
    state.fatigue = min(0.9, state.fatigue + row["annoyance_penalty"])
    return outcome


def apply_outcome(state: InvoiceState, action: str, outcome: str, today: date, audit_trail: list):
    entry = {
        "invoice_id": state.invoice_id,
        "customer_id": state.customer_id,
        "date": today.isoformat(),
        "action": action,
        "outcome": outcome,
        "remaining_amount_before": round(state.remaining_amount, 2),
    }

    if outcome == "pay":
        entry["amount_recovered"] = round(state.remaining_amount, 2)
        state.remaining_amount = 0.0
        state.status = "paid"

    elif outcome == "partial":
        partial_fraction = random.uniform(0.25, 0.6)
        recovered = round(state.remaining_amount * partial_fraction, 2)
        state.remaining_amount = round(state.remaining_amount - recovered, 2)
        entry["amount_recovered"] = recovered
        # stays "overdue" -- remainder still owed, chasing continues

    elif outcome == "promise":
        promise_horizon = random.randint(7, 14)
        state.promise_date = today + timedelta(days=promise_horizon)
        state.status = "promised"
        entry["amount_recovered"] = 0.0
        entry["promise_date"] = state.promise_date.isoformat()

    else:  # ignore
        entry["amount_recovered"] = 0.0

    if outcome != "promise":
        state.prior_contact_count += 1
        state.last_contact_date = today
        state.action_history.append((action, "ignore" if outcome == "ignore" else outcome))
    else:
        state.prior_contact_count += 1
        state.last_contact_date = today
        state.action_history.append((action, "promise"))

    entry["remaining_amount_after"] = round(state.remaining_amount, 2)
    entry["status_after"] = state.status
    audit_trail.append(entry)


def resolve_promises(states: dict, customers_by_id: dict, today: date, audit_trail: list):
    for state in states.values():
        if state.status == "promised" and state.promise_date is not None and today >= state.promise_date:
            hist_score = customers_by_id[state.customer_id]["payment_history_score"]
            fulfilled = random.random() < hist_score  # more reliable customers keep promises more often

            entry = {
                "invoice_id": state.invoice_id,
                "customer_id": state.customer_id,
                "date": today.isoformat(),
                "action": "promise_resolution",
            }

            if fulfilled:
                entry["outcome"] = "promise_kept"
                entry["amount_recovered"] = round(state.remaining_amount, 2)
                state.remaining_amount = 0.0
                state.status = "paid"
            else:
                entry["outcome"] = "promise_broken"
                entry["amount_recovered"] = 0.0
                state.status = "overdue"  # resume chasing, not exhausted

            entry["status_after"] = state.status
            audit_trail.append(entry)


def run_simulation(decide_fn=decide_next_action, seed=11, policy=None, gated=False,
                    resume_states=None, resume_audit_trail=None, resume_pending=None):
    """
    gated=False (default): old behavior, used for Day 3/4/5 batch comparisons --
      human-approval-required actions execute immediately and are just logged
      as an approval event (auto-approved for batch analysis purposes).
    gated=True: REAL gate. When an action requires human approval, the
      invoice's outcome is NOT sampled -- it's marked 'awaiting_approval'
      and excluded from further decisions until resolved by
      src/resolve_approvals.py, which uses the same real data and the same
      real hidden response model, just triggered by an actual human
      decision instead of auto-approval.

    resume_states / resume_audit_trail / resume_pending: pass these to
    continue a simulation using state that was previously paused and then
    resolved via the approval CLI, instead of starting fresh.
    """
    policy = policy or POLICY

    if resume_states is not None:
        states = resume_states
        _, customers_by_id = load_states()  # reload static reference data (real, not fabricated)
        audit_trail = resume_audit_trail if resume_audit_trail is not None else []
        pending_human_approvals = resume_pending if resume_pending is not None else []
        random.seed(seed + 1)  # new process, new seed -- documented, not hidden
    else:
        random.seed(seed)
        states, customers_by_id = load_states()
        audit_trail = []
        pending_human_approvals = []

    response_model = load_hidden_response_model()

    for day_offset in range(SIM_DAYS):
        today = SIM_START_DATE + timedelta(days=day_offset)

        resolve_promises(states, customers_by_id, today, audit_trail)

        for state in states.values():
            if state.status in policy["stopping_statuses"]:
                continue

            decision = decide_fn(state, today, policy)

            if decision.action == "wait":
                continue

            if decision.requires_human_approval:
                if gated:
                    # REAL gate: do not act. Park the invoice.
                    state.status = "awaiting_approval"
                    state.pending_action = decision.action
                    state.pending_reason = decision.reason
                    state.pending_since_day = day_offset
                    pending_human_approvals.append({
                        "invoice_id": state.invoice_id,
                        "customer_id": state.customer_id,
                        "date": today.isoformat(),
                        "action": decision.action,
                        "reason": decision.reason,
                        "importance_score": state.importance_score,
                        "remaining_amount": round(state.remaining_amount, 2),
                        "days_overdue": state.days_overdue,
                        "resolution": "PENDING",
                    })
                    audit_trail.append({
                        "invoice_id": state.invoice_id,
                        "customer_id": state.customer_id,
                        "date": today.isoformat(),
                        "action": decision.action,
                        "outcome": "gated_pending_approval",
                        "amount_recovered": 0.0,
                        "status_after": "awaiting_approval",
                    })
                    continue
                else:
                    pending_human_approvals.append({
                        "invoice_id": state.invoice_id,
                        "date": today.isoformat(),
                        "action": decision.action,
                        "reason": decision.reason,
                        "resolution": "auto-approved for simulation",
                    })

            outcome = sample_outcome(state, decision.action, response_model)
            apply_outcome(state, decision.action, outcome, today, audit_trail)

    return states, audit_trail, pending_human_approvals


def summarize(states: dict, audit_trail: list, pending_human_approvals: list):
    total_original = sum(s.original_amount for s in states.values())
    total_recovered = sum(e.get("amount_recovered", 0) for e in audit_trail)
    total_recovered += sum(e.get("amount_recovered", 0) for e in audit_trail if e.get("action") == "promise_resolution")
    # avoid double count: recompute cleanly
    total_recovered = sum(e["amount_recovered"] for e in audit_trail if "amount_recovered" in e)

    status_counts = {}
    for s in states.values():
        status_counts[s.status] = status_counts.get(s.status, 0) + 1

    action_counts = {}
    for e in audit_trail:
        a = e.get("action")
        if a and a != "promise_resolution":
            action_counts[a] = action_counts.get(a, 0) + 1

    exceptions = [s.invoice_id for s in states.values() if s.status == "exhausted"]

    print("=" * 60)
    print("SIMULATION SUMMARY")
    print("=" * 60)
    print(f"Total invoices:          {len(states)}")
    print(f"Total original amount:   INR {total_original:,.2f}")
    print(f"Total recovered:         INR {total_recovered:,.2f}")
    print(f"Recovery rate:           {100*total_recovered/total_original:.1f}%")
    print(f"\nFinal status breakdown:")
    for k, v in sorted(status_counts.items()):
        print(f"  {k:12s}: {v}")
    print(f"\nActions taken (excl. promise resolutions):")
    for k, v in sorted(action_counts.items()):
        print(f"  {k:22s}: {v}")
    print(f"\nExceptions (exhausted, unresolved): {len(exceptions)}")
    print(f"Human approvals required during run: {len(pending_human_approvals)}")
    print(f"Total audit trail entries: {len(audit_trail)}")
    print("=" * 60)

    return {
        "total_original": total_original,
        "total_recovered": total_recovered,
        "recovery_rate_pct": 100 * total_recovered / total_original,
        "status_counts": status_counts,
        "action_counts": action_counts,
        "exceptions": exceptions,
        "human_approvals_count": len(pending_human_approvals),
    }


if __name__ == "__main__":
    states, audit_trail, pending_approvals = run_simulation()
    summary = summarize(states, audit_trail, pending_approvals)

    # save outputs for inspection / later dashboard use
    pd.DataFrame(audit_trail).to_csv(DATA_DIR / "audit_trail_run1.csv", index=False)
    pd.DataFrame(pending_approvals).to_csv(DATA_DIR / "human_approvals_run1.csv", index=False)
    print(f"\nSaved: data/audit_trail_run1.csv ({len(audit_trail)} rows)")
    print(f"Saved: data/human_approvals_run1.csv ({len(pending_approvals)} rows)")