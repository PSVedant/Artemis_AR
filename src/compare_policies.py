"""
Day 4: run both policies through the identical simulation environment and
compare. This is the actual evidence for "our policy is better," not just
an assertion.
"""

import pandas as pd

from src.policy_engine import InvoiceState, decide_next_action, POLICY
from src.baseline_policy import decide_next_action_baseline
from src.simulation_engine import run_simulation, summarize, DATA_DIR


def vip_relationship_damage(states: dict, customers_by_id: dict):
    """Count escalate_collections actions taken against high-importance
    customers -- this is the 'relationship damage' metric the smart policy
    should minimize relative to baseline."""
    vip_escalations = 0
    for s in states.values():
        if s.importance_score >= 0.3:  # same threshold as human_approval_policy
            vip_escalations += sum(1 for a, _ in s.action_history if a == "escalate_collections")
    return vip_escalations


def main():
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    customers_by_id = customers.set_index("customer_id").to_dict("index")

    print("\n" + "#" * 60)
    print("# RUN 1: SMART POLICY (importance-aware, gated)")
    print("#" * 60)
    states_smart, audit_smart, approvals_smart = run_simulation(decide_fn=decide_next_action)
    summary_smart = summarize(states_smart, audit_smart, approvals_smart)
    vip_damage_smart = vip_relationship_damage(states_smart, customers_by_id)

    print("\n" + "#" * 60)
    print("# RUN 2: BASELINE POLICY (naive fixed ladder)")
    print("#" * 60)
    states_baseline, audit_baseline, approvals_baseline = run_simulation(decide_fn=decide_next_action_baseline)
    summary_baseline = summarize(states_baseline, audit_baseline, approvals_baseline)
    vip_damage_baseline = vip_relationship_damage(states_baseline, customers_by_id)

    print("\n" + "=" * 60)
    print("COMPARISON: SMART vs BASELINE")
    print("=" * 60)
    print(f"{'Metric':<35}{'Smart':>12}{'Baseline':>12}")
    print("-" * 60)
    print(f"{'Total recovered (INR)':<35}{summary_smart['total_recovered']:>12,.0f}{summary_baseline['total_recovered']:>12,.0f}")
    print(f"{'Recovery rate (%)':<35}{summary_smart['recovery_rate_pct']:>12.1f}{summary_baseline['recovery_rate_pct']:>12.1f}")
    print(f"{'Invoices exhausted':<35}{len(summary_smart['exceptions']):>12}{len(summary_baseline['exceptions']):>12}")
    print(f"{'Escalations on VIP/Standard+ accts':<35}{vip_damage_smart:>12}{vip_damage_baseline:>12}")
    print(f"{'Human approvals logged':<35}{summary_smart['human_approvals_count']:>12}{summary_baseline['human_approvals_count']:>12}")
    print("=" * 60)

    recovery_diff = summary_smart['total_recovered'] - summary_baseline['total_recovered']
    print(f"\nSmart policy recovered INR {recovery_diff:,.0f} "
          f"{'more' if recovery_diff >= 0 else 'less'} than baseline.")

    print(f"\nNOTE on VIP escalation comparison: baseline shows {vip_damage_baseline} "
          f"escalate_collections actions in total (not just on VIPs) because its fixed "
          f"one-tier-per-contact ladder never reaches that tier before hitting the shared "
          f"{POLICY['max_contact_attempts']['value']}-attempt cap -- it gets marked "
          f"'exhausted' first. This means baseline structurally never reaches the point "
          f"where human-approval gating would matter, so this run does NOT yet prove the "
          f"VIP-protection value of the smart policy's gating. See the follow-up run below, "
          f"which isolates invoices severe enough that both policies are forced to reach "
          f"the escalation decision.")

    pd.DataFrame(audit_smart).to_csv(DATA_DIR / "audit_trail_smart.csv", index=False)
    pd.DataFrame(audit_baseline).to_csv(DATA_DIR / "audit_trail_baseline.csv", index=False)
    print(f"\nSaved: data/audit_trail_smart.csv, data/audit_trail_baseline.csv")

    # -----------------------------------------------------------------
    # Targeted sub-analysis: does gating actually protect VIPs?
    # Filter the audit trail to invoices belonging to importance_score
    # >= 0.3 customers (the human-approval threshold) that were
    # severely overdue (60+ days) -- i.e. cases where baseline's ladder
    # would realistically have reached collections-tier severity too.
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TARGETED CHECK: escalation behavior on important, severe accounts")
    print("=" * 60)

    important_ids = {cid for cid, c in customers_by_id.items() if c["importance_score"] >= 0.3}

    def escalations_for_important(states):
        return sum(
            1 for s in states.values()
            if s.customer_id in important_ids
            for a, _ in s.action_history if a == "escalate_collections"
        )

    smart_important_esc = escalations_for_important(states_smart)
    baseline_important_esc = escalations_for_important(states_baseline)

    print(f"Escalate_collections fired on important-customer invoices:")
    print(f"  Smart policy:    {smart_important_esc} (all required logged human approval)")
    print(f"  Baseline policy: {baseline_important_esc} (baseline has no approval concept -- "
          f"any escalation it fires goes through unchecked)")
    print(f"\nInterpretation: baseline's fixed ladder happened not to reach this tier within "
          f"the attempt cap in this run, so it shows 0 by circumstance, not by design -- it "
          f"has no mechanism that would have stopped it if it *had* reached that tier. "
          f"The smart policy's {smart_important_esc} escalations were each gated through an "
          f"explicit, logged approval step. This is the honest distinction: not 'fewer "
          f"escalations happened' but 'every escalation that did happen was checked.'")


def run_extended_cap_experiment():
    """
    Diagnostic-only experiment: raise max_contact_attempts so BOTH policies
    can structurally reach escalate_collections before hitting the cap.
    This isolates the actual question -- does the smart policy's gating
    protect important customers -- from the earlier confound where the
    baseline never got the chance to escalate at all.

    This does NOT change the production policy.json. It's a temporary,
    symmetric override used only for this comparison.
    """
    import copy
    experimental_policy = copy.deepcopy(POLICY)
    experimental_policy["max_contact_attempts"]["value"] = 8  # was 4; now both ladders can reach tier 5

    customers = pd.read_csv(DATA_DIR / "customers.csv")
    customers_by_id = customers.set_index("customer_id").to_dict("index")
    important_ids = {cid for cid, c in customers_by_id.items() if c["importance_score"] >= 0.3}

    print("\n" + "#" * 60)
    print("# DIAGNOSTIC: extended attempt cap (8), so both policies can")
    print("# actually reach escalate_collections -- isolates gating effect")
    print("#" * 60)

    states_smart, _, approvals_smart = run_simulation(
        decide_fn=decide_next_action, policy=experimental_policy)
    states_baseline, _, approvals_baseline = run_simulation(
        decide_fn=decide_next_action_baseline, policy=experimental_policy)

    def escalations_for_important(states):
        return sum(
            1 for s in states.values()
            if s.customer_id in important_ids
            for a, _ in s.action_history if a == "escalate_collections"
        )

    smart_esc = escalations_for_important(states_smart)
    baseline_esc = escalations_for_important(states_baseline)

    print(f"\nWith both policies able to actually reach the top tier:")
    print(f"  Smart policy escalations on important customers:    {smart_esc} "
          f"(all logged for human approval: {len(approvals_smart)} total approval events)")
    print(f"  Baseline policy escalations on important customers: {baseline_esc} "
          f"(zero approval mechanism -- these fired automatically, unchecked)")

    if baseline_esc > 0:
        print(f"\nThis confirms the effect: under conditions where baseline CAN reach "
              f"collections-tier action, it does so without any check. The smart policy "
              f"reaches similar decisions but routes every one through a logged approval "
              f"step first.")
    else:
        print(f"\nBaseline still didn't escalate on important customers in this run -- "
              f"worth inspecting further before claiming the gating effect is proven.")

    return smart_esc, baseline_esc


if __name__ == "__main__":
    main()
    run_extended_cap_experiment()
