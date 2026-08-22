"""
Day 6, Phase 2: resolve the invoices that Phase 1 genuinely paused.

For each invoice awaiting approval, this shows the REAL data (customer,
amount, importance, reason it triggered) and asks you to approve or deny.

Approve  -> the action executes for real: an outcome is sampled from the
            actual hidden response model (data/ground_truth_HIDDEN.csv) for
            that specific invoice + action, exactly as it would have if it
            weren't gated. Nothing about the outcome is fabricated here --
            it's the same environment logic used throughout, just triggered
            by your real decision instead of an auto-approval.
Deny     -> the invoice is marked 'manual_review_denied' -- a genuine,
            honest exception. It does not get auto-resolved by any other
            action.

After resolving all pending cases, this resumes the simulation so any
newly-freed invoices can continue being contacted for the remaining days.
"""

import sys

import pandas as pd

from src.policy_engine import decide_next_action, InvoiceState
from src.simulation_engine import (
    run_simulation, load_hidden_response_model, sample_outcome, apply_outcome,
    DATA_DIR, SIM_START_DATE,
)
from src.state_io import load_states_from_file, save_states
from datetime import timedelta

STATE_FILE = DATA_DIR / "gated_run_state.json"


def resolve_one(state: InvoiceState, response_model: dict, audit_trail: list, customers_by_id: dict):
    action = state.pending_action
    reason = state.pending_reason
    day_offset = state.pending_since_day
    today = SIM_START_DATE + timedelta(days=day_offset)

    cust = customers_by_id[state.customer_id]

    print("\n" + "-" * 60)
    print(f"Invoice:            {state.invoice_id}")
    print(f"Customer:           {cust['customer_name']} ({cust['relationship_tier']})")
    print(f"Importance score:   {state.importance_score}")
    print(f"Remaining amount:   INR {state.remaining_amount:,.2f}")
    print(f"Days overdue:       {state.days_overdue}")
    print(f"Proposed action:    {action}")
    print(f"Policy's reasoning: {reason}")
    print("-" * 60)

    while True:
        choice = input("Approve this escalation? [y/n]: ").strip().lower()
        if choice in ("y", "yes"):
            approved = True
            break
        elif choice in ("n", "no"):
            approved = False
            break
        print("Please type y or n.")

    if approved:
        outcome = sample_outcome(state, action, response_model)
        state.status = "overdue"  # clear the gate before apply_outcome sets the real resulting status
        apply_outcome(state, action, outcome, today, audit_trail)
        audit_trail[-1]["human_decision"] = "approved"
        print(f"-> Approved. Real outcome sampled: {outcome}. "
              f"Amount recovered this action: INR {audit_trail[-1].get('amount_recovered', 0):,.2f}")
    else:
        state.status = "manual_review_denied"
        audit_trail.append({
            "invoice_id": state.invoice_id,
            "customer_id": state.customer_id,
            "date": today.isoformat(),
            "action": action,
            "outcome": "escalation_denied",
            "amount_recovered": 0.0,
            "status_after": "manual_review_denied",
            "human_decision": "denied",
        })
        print("-> Denied. Invoice marked for manual review, excluded from further automated contact.")

    state.pending_action = None
    state.pending_reason = None
    state.pending_since_day = None


def main():
    if not STATE_FILE.exists():
        print("No gated run found. Run: python -m src.run_gated_simulation first.")
        sys.exit(1)

    states = load_states_from_file(STATE_FILE)
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    customers_by_id = customers.set_index("customer_id").to_dict("index")
    response_model = load_hidden_response_model()

    pending = [s for s in states.values() if s.status == "awaiting_approval"]

    if not pending:
        print("No invoices are currently awaiting approval.")
        sys.exit(0)

    print(f"{len(pending)} invoice(s) awaiting your approval.\n")

    audit_trail = pd.read_csv(DATA_DIR / "audit_trail_gated.csv").to_dict("records") \
        if (DATA_DIR / "audit_trail_gated.csv").exists() else []

    for state in pending:
        resolve_one(state, response_model, audit_trail, customers_by_id)

    print("\nAll pending approvals resolved. Resuming simulation for remaining days...")
    states, audit_trail, pending_approvals = run_simulation(
        decide_fn=decide_next_action, gated=True,
        resume_states=states, resume_audit_trail=audit_trail, resume_pending=[],
    )

    save_states(states, STATE_FILE)
    pd.DataFrame(audit_trail).to_csv(DATA_DIR / "audit_trail_gated.csv", index=False)

    still_pending = [p for p in pending_approvals if p["resolution"] == "PENDING"]
    print(f"\nResumed run complete. New approvals now pending: {len(still_pending)}")
    if still_pending:
        print("Run this script again to resolve them.")

    status_counts = {}
    for s in states.values():
        status_counts[s.status] = status_counts.get(s.status, 0) + 1
    print(f"\nFinal status breakdown: {status_counts}")


if __name__ == "__main__":
    main()
