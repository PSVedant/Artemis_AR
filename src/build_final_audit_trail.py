"""
Day 7: build the final, canonical audit trail.

This takes YOUR real gated run's audit trail (data/audit_trail_gated.csv --
built from your actual approve/deny decisions in Day 6) and attaches a
drafted message to every real contact action, using each customer's real
language_pref. This becomes the single source of truth used for the
dashboard/demo (Day 8/9) -- not the earlier auto-approve batch run.

Nothing here is fabricated: every row comes from your actual gated
simulation + your actual approval decisions. Messages are drafted fresh
against that real data, with the same graceful LLM-fallback behavior as
Day 5.
"""

import time

import pandas as pd

from src.message_drafter import draft_message
from src.simulation_engine import DATA_DIR

GATED_AUDIT_PATH = DATA_DIR / "audit_trail_gated.csv"
FINAL_AUDIT_PATH = DATA_DIR / "final_audit_trail.csv"


def build_final_audit_trail(use_llm=True, pace_seconds=0.0):
    if not GATED_AUDIT_PATH.exists():
        raise FileNotFoundError(
            "data/audit_trail_gated.csv not found. Run src.run_gated_simulation "
            "and src.resolve_approvals first (Day 6) before this."
        )

    audit = pd.read_csv(GATED_AUDIT_PATH)
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    invoices = pd.read_csv(DATA_DIR / "invoices.csv")
    customers_by_id = customers.set_index("customer_id").to_dict("index")
    invoices_by_id = invoices.set_index("invoice_id").to_dict("index")

    contact_mask = audit["action"].notna() & ~audit["action"].isin(
        ["promise_resolution", "gated_pending_approval"]
    )
    contact_rows = audit[contact_mask]
    total = len(contact_rows)
    print(f"Drafting messages for {total} real contact actions from your gated run...")

    message_lang, message_source, message_reason, message_text = [], [], [], []
    llm_count = fallback_count = 0
    processed = 0
    start = time.time()

    for _, row in audit.iterrows():
        action = row.get("action")
        if pd.isna(action) or action in ("promise_resolution", "gated_pending_approval"):
            message_lang.append(None)
            message_source.append(None)
            message_reason.append(None)
            message_text.append(None)
            continue

        inv_id = row["invoice_id"]
        cust_id = row["customer_id"]
        cust = customers_by_id.get(cust_id)
        inv = invoices_by_id.get(inv_id)

        if cust is None or inv is None:
            message_lang.append(None)
            message_source.append(None)
            message_reason.append("customer/invoice not found in master data")
            message_text.append(None)
            continue

        msg = draft_message(
            invoice_id=inv_id,
            action=action,
            language=cust["language_pref"],
            customer_name=cust["customer_name"],
            amount=row.get("remaining_amount_before", inv["invoice_amount"]),
            due_date=inv["due_date"],
            days_overdue=inv["days_overdue"],
            use_llm=use_llm,
        )

        message_lang.append(msg.language)
        message_source.append(msg.source)
        message_reason.append(msg.fallback_reason)
        message_text.append(msg.text)

        if msg.source == "llm":
            llm_count += 1
        else:
            fallback_count += 1

        processed += 1
        if processed % 10 == 0 or processed == total:
            print(f"  [{processed}/{total}] {time.time()-start:.0f}s elapsed "
                  f"({llm_count} llm, {fallback_count} fallback)")

        if use_llm and pace_seconds:
            time.sleep(pace_seconds)

    audit["message_language"] = message_lang
    audit["message_source"] = message_source
    audit["message_fallback_reason"] = message_reason
    audit["message_text"] = message_text

    audit.to_csv(FINAL_AUDIT_PATH, index=False)
    print(f"\nSaved: data/final_audit_trail.csv ({len(audit)} rows)")
    print(f"Messages: {llm_count} via LLM, {fallback_count} via template fallback")

    return audit


if __name__ == "__main__":
    import os
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    pace = 2.5 if provider == "groq" else 0.0
    build_final_audit_trail(use_llm=True, pace_seconds=pace)
