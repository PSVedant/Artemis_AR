"""
Day 5 integration: runs the smart-policy simulation, then drafts an actual
message for every contact action in the audit trail, using each customer's
language_pref. Produces an audit trail enriched with real message text and
a record of how many messages needed the template fallback vs the LLM.
"""

import time
import pandas as pd

from src.policy_engine import decide_next_action
from src.simulation_engine import run_simulation, DATA_DIR
from src.message_drafter import draft_message


def enrich_audit_trail_with_messages(use_llm=True, pace_seconds=0.0):
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    invoices = pd.read_csv(DATA_DIR / "invoices.csv")
    customers_by_id = customers.set_index("customer_id").to_dict("index")
    invoices_by_id = invoices.set_index("invoice_id").to_dict("index")

    states, audit_trail, approvals = run_simulation(decide_fn=decide_next_action)

    contact_entries = [e for e in audit_trail if e.get("action") not in (None, "promise_resolution")]
    total = len(contact_entries)
    print(f"Drafting messages for {total} contact actions"
          + (f" (pacing {pace_seconds}s between calls)" if pace_seconds else "") + "...")

    enriched = []
    llm_count = 0
    fallback_count = 0
    start = time.time()
    processed = 0

    for entry in audit_trail:
        action = entry.get("action")
        if action in (None, "promise_resolution"):
            enriched.append(entry)
            continue

        inv_id = entry["invoice_id"]
        cust_id = entry["customer_id"]
        cust = customers_by_id[cust_id]
        inv = invoices_by_id[inv_id]

        msg = draft_message(
            invoice_id=inv_id,
            action=action,
            language=cust["language_pref"],
            customer_name=cust["customer_name"],
            amount=entry.get("remaining_amount_before", inv["invoice_amount"]),
            due_date=inv["due_date"],
            days_overdue=inv["days_overdue"],
            use_llm=use_llm,
        )

        entry["message_language"] = msg.language
        entry["message_source"] = msg.source
        entry["message_fallback_reason"] = msg.fallback_reason
        entry["message_text"] = msg.text

        if msg.source == "llm":
            llm_count += 1
        else:
            fallback_count += 1

        enriched.append(entry)
        processed += 1

        if processed % 10 == 0 or processed == total:
            elapsed = time.time() - start
            print(f"  [{processed}/{total}] {elapsed:.0f}s elapsed "
                  f"({llm_count} llm, {fallback_count} fallback)")

        if use_llm and pace_seconds:
            time.sleep(pace_seconds)

    print(f"\nDone in {time.time()-start:.0f}s. Messages drafted: {llm_count} via LLM, {fallback_count} via template fallback")
    return enriched, states


if __name__ == "__main__":
    import os
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    pace = 2.1 if provider == "groq" else 0.0  # stay under Groq's ~30 req/min free-tier limit

    enriched_trail, states = enrich_audit_trail_with_messages(use_llm=True, pace_seconds=pace)
    df = pd.DataFrame(enriched_trail)
    df.to_csv(DATA_DIR / "audit_trail_with_messages.csv", index=False)
    print(f"Saved: data/audit_trail_with_messages.csv ({len(df)} rows)")

    # show a couple of real examples
    contact_rows = df[df["action"].notna() & (df["action"] != "promise_resolution")]
    print("\n--- Sample drafted messages ---")
    for _, row in contact_rows.head(3).iterrows():
        print(f"\n[{row['invoice_id']}] {row['action']} ({row['message_language']}, "
              f"source={row['message_source']})")
        print(row["message_text"])
