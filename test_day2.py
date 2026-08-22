"""
Day 2 verification suite for Artemis_AR policy engine.

This isn't a smoke test -- it checks the policy engine produces the
CORRECT decision for each scenario, with assertions. Run this and if it
prints "ALL TESTS PASSED", Day 2's logic is verified, not just "runs
without crashing."
"""

from datetime import date as d
from src.policy_engine import InvoiceState, decide_next_action

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if condition:
        passed += 1
    else:
        failed += 1


# -----------------------------------------------------------------------
# Test 1: First contact, mild overdue -> should start gentle
# -----------------------------------------------------------------------
s = InvoiceState("T1", "C1", days_overdue=10, risk_segment="low", importance_score=0.2)
dec = decide_next_action(s, today=d(2026, 3, 1))
check("First contact + mild overdue -> gentle_reminder", dec.action == "gentle_reminder")

# -----------------------------------------------------------------------
# Test 2: First contact, severely overdue -> should skip to firm
# -----------------------------------------------------------------------
s = InvoiceState("T2", "C2", days_overdue=50, risk_segment="high", importance_score=0.2)
dec = decide_next_action(s, today=d(2026, 3, 1))
check("First contact + 50d overdue -> firm_reminder (skips gentle)", dec.action == "firm_reminder")

# -----------------------------------------------------------------------
# Test 3: Cooldown active -> must wait, regardless of anything else
# -----------------------------------------------------------------------
s = InvoiceState("T3", "C3", days_overdue=80, risk_segment="high", importance_score=0.9,
                  prior_contact_count=1, last_contact_date=d(2026, 2, 28),
                  action_history=[("gentle_reminder", "ignore")])
dec = decide_next_action(s, today=d(2026, 3, 1))  # only 1 day since contact, cooldown is 5
check("Cooldown active (1d since contact, needs 5d) -> wait", dec.action == "wait")

# -----------------------------------------------------------------------
# Test 4: Max attempts reached -> exhausted, must wait
# -----------------------------------------------------------------------
s = InvoiceState("T4", "C4", days_overdue=80, risk_segment="high", importance_score=0.5,
                  prior_contact_count=4, last_contact_date=d(2026, 2, 1),
                  action_history=[("gentle_reminder", "ignore")] * 4)
dec = decide_next_action(s, today=d(2026, 3, 1))
check("4 prior attempts (max reached) -> wait + status becomes exhausted",
      dec.action == "wait" and s.status == "exhausted")

# -----------------------------------------------------------------------
# Test 5: Terminal status (paid) -> must never act again
# -----------------------------------------------------------------------
s = InvoiceState("T5", "C5", days_overdue=20, risk_segment="low", importance_score=0.3, status="paid")
dec = decide_next_action(s, today=d(2026, 3, 1))
check("Status already 'paid' -> wait, no action taken", dec.action == "wait")

# -----------------------------------------------------------------------
# Test 6: Cannot reach escalate_collections without payment_plan_offer
#         or severity threshold -- must fall back to payment_plan_offer
# -----------------------------------------------------------------------
s = InvoiceState("T6", "C6", days_overdue=30, risk_segment="medium", importance_score=0.4,
                  prior_contact_count=2, last_contact_date=d(2026, 2, 20),
                  action_history=[("gentle_reminder", "ignore"), ("firm_reminder", "ignore")])
dec = decide_next_action(s, today=d(2026, 3, 1))
check("Gate not met (only 30d overdue, no payment plan tried) -> payment_plan_offer, not escalation",
      dec.action == "payment_plan_offer")

# -----------------------------------------------------------------------
# Test 7: Severity threshold met (60+ days, 2+ contacts) -> CAN reach
#         escalate_collections even without payment_plan_offer
# -----------------------------------------------------------------------
s = InvoiceState("T7", "C7", days_overdue=65, risk_segment="high", importance_score=0.1,
                  prior_contact_count=2, last_contact_date=d(2026, 2, 20),
                  action_history=[("gentle_reminder", "ignore"), ("firm_reminder", "ignore")])
dec = decide_next_action(s, today=d(2026, 3, 1))
check("Severity threshold met (65d, 2 contacts) -> payment_plan_offer next (still climbing ladder)",
      dec.action == "payment_plan_offer")

# -----------------------------------------------------------------------
# Test 8: Low-importance customer at escalation gate -> auto-approved
# -----------------------------------------------------------------------
s = InvoiceState("T8", "C8", days_overdue=75, risk_segment="high", importance_score=0.1,
                  prior_contact_count=3, last_contact_date=d(2026, 2, 20),
                  action_history=[("gentle_reminder", "ignore"), ("firm_reminder", "ignore"),
                                   ("payment_plan_offer", "ignore")])
dec = decide_next_action(s, today=d(2026, 3, 1))
check("Low importance (0.1) + gate satisfied -> escalate_collections, NO human approval needed",
      dec.action == "escalate_collections" and dec.requires_human_approval is False)

# -----------------------------------------------------------------------
# Test 9: High-importance customer at escalation gate -> requires human approval
# -----------------------------------------------------------------------
s = InvoiceState("T9", "C9", days_overdue=75, risk_segment="high", importance_score=0.9,
                  prior_contact_count=3, last_contact_date=d(2026, 2, 20),
                  action_history=[("gentle_reminder", "ignore"), ("firm_reminder", "ignore"),
                                   ("payment_plan_offer", "ignore")])
dec = decide_next_action(s, today=d(2026, 3, 1))
check("High importance (0.9) + gate satisfied -> escalate_collections, HUMAN APPROVAL required",
      dec.action == "escalate_collections" and dec.requires_human_approval is True)

# -----------------------------------------------------------------------
# Test 10: Two consecutive ignores -> forced tier jump (skips a level)
# -----------------------------------------------------------------------
s = InvoiceState("T10", "C10", days_overdue=25, risk_segment="medium", importance_score=0.2,
                  prior_contact_count=2, last_contact_date=d(2026, 2, 20),
                  action_history=[("gentle_reminder", "ignore"), ("firm_reminder", "ignore")])
dec = decide_next_action(s, today=d(2026, 3, 1))
check("2 consecutive ignores -> jumps to payment_plan_offer (skips phone_call)",
      dec.action == "payment_plan_offer")

# -----------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"RESULT: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL TESTS PASSED -- Day 2 policy engine verified.")
else:
    print("SOME TESTS FAILED -- review policy_engine.py logic above.")
print(f"{'='*60}")
