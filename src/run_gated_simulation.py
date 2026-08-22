"""
Day 6, Phase 1: run the simulation with REAL gating.

Unlike Day 3/4/5's runs (which auto-approve for batch comparison purposes),
this run genuinely stops any action that requires human approval. Those
invoices sit in 'awaiting_approval' -- no money moves, no outcome is
sampled -- until you resolve them via src/resolve_approvals.py.

Run this first, then run resolve_approvals.py to see and act on the real
pending cases.
"""

import pandas as pd

from src.policy_engine import decide_next_action
from src.simulation_engine import run_simulation, DATA_DIR
from src.state_io import save_states

STATE_FILE = DATA_DIR / "gated_run_state.json"


def main():
    print("Running gated simulation (Phase 1)...")
    states, audit_trail, pending = run_simulation(decide_fn=decide_next_action, gated=True)

    truly_pending = [p for p in pending if p["resolution"] == "PENDING"]

    print(f"\nSimulation complete.")
    print(f"Total invoices: {len(states)}")
    print(f"Genuinely paused, awaiting human approval: {len(truly_pending)}")

    save_states(states, STATE_FILE)
    pd.DataFrame(audit_trail).to_csv(DATA_DIR / "audit_trail_gated.csv", index=False)
    pd.DataFrame(pending).to_csv(DATA_DIR / "pending_approvals_gated.csv", index=False)

    print(f"\nSaved: data/gated_run_state.json (full state, for resolve_approvals.py)")
    print(f"Saved: data/audit_trail_gated.csv ({len(audit_trail)} rows)")
    print(f"Saved: data/pending_approvals_gated.csv ({len(pending)} rows)")

    if truly_pending:
        print(f"\n{len(truly_pending)} invoices are genuinely blocked, waiting on you.")
        print("Run: python -m src.resolve_approvals")
    else:
        print("\nNo invoices required approval in this run (may happen with a different seed).")


if __name__ == "__main__":
    main()
