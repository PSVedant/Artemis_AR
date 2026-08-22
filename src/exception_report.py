"""
Day 7: exception report -- the honest "what we couldn't resolve" summary.

Built from your real gated_run_state.json (the actual final state after
your real approve/deny decisions). No fabrication: every row here reflects
a real invoice that is genuinely NOT paid, with the real reason it's stuck.
"""

import pandas as pd

from src.state_io import load_states_from_file
from src.simulation_engine import DATA_DIR

STATE_FILE = DATA_DIR / "gated_run_state.json"
EXCEPTION_REPORT_PATH = DATA_DIR / "exception_report.csv"

EXCEPTION_REASONS = {
    "exhausted": "Reached maximum contact attempts without payment, promise, or resolution -- needs manual outreach.",
    "manual_review_denied": "Escalation to collections was proposed but a human reviewer denied it -- needs a manual decision on next steps.",
    "awaiting_approval": "Still waiting on a human approval decision -- should not appear if Day 6 was fully resolved.",
}


def build_exception_report():
    if not STATE_FILE.exists():
        raise FileNotFoundError("data/gated_run_state.json not found. Run Day 6 first.")

    states = load_states_from_file(STATE_FILE)
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    customers_by_id = customers.set_index("customer_id").to_dict("index")

    rows = []
    total_at_risk = 0.0
    total_recovered = 0.0
    total_original = 0.0

    for s in states.values():
        total_original += s.original_amount
        if s.status == "paid":
            total_recovered += s.original_amount  # fully recovered invoices
            continue
        elif s.status in ("promised",):
            # not yet resolved at report time -- shouldn't happen at end of
            # a full run, but flag honestly if it does
            reason = "Customer promised payment; promise not yet due/resolved at report time."
        else:
            reason = EXCEPTION_REASONS.get(s.status, f"Unrecognized terminal status: {s.status}")

        cust = customers_by_id.get(s.customer_id, {})
        rows.append({
            "invoice_id": s.invoice_id,
            "customer_id": s.customer_id,
            "customer_name": cust.get("customer_name", "UNKNOWN"),
            "relationship_tier": cust.get("relationship_tier", "UNKNOWN"),
            "status": s.status,
            "original_amount": s.original_amount,
            "remaining_amount": s.remaining_amount,
            "days_overdue_at_invoice_creation": s.days_overdue,
            "prior_contact_count": s.prior_contact_count,
            "reason": reason,
        })
        total_at_risk += s.remaining_amount

    df = pd.DataFrame(rows).sort_values("remaining_amount", ascending=False)
    df.to_csv(EXCEPTION_REPORT_PATH, index=False)

    print("=" * 60)
    print("EXCEPTION REPORT (honest, unresolved cases)")
    print("=" * 60)
    print(f"Total invoices:            {len(states)}")
    print(f"Fully paid:                {len(states) - len(rows)}")
    print(f"Exceptions (unresolved):   {len(rows)}")
    print(f"\nBreakdown by status:")
    print(df["status"].value_counts().to_string())
    print(f"\nTotal original amount (all invoices): INR {total_original:,.2f}")
    print(f"Total recovered:                       INR {total_recovered:,.2f}")
    print(f"Total still at risk (exceptions):      INR {total_at_risk:,.2f}")
    print(f"Recovery rate:                          {100*total_recovered/total_original:.1f}%")
    print("=" * 60)
    print(f"\nSaved: data/exception_report.csv ({len(df)} rows)")

    return df


if __name__ == "__main__":
    build_exception_report()
