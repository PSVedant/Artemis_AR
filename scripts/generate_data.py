"""
Synthetic B2B receivables (dunning) dataset generator — v2.

Adds a customer master table so the agent can factor in relationship
importance (VIP vs standard) when choosing how aggressively to chase an
overdue invoice, mirroring how real AR teams operate.

Produces:
  - customers.csv               : customer master (agent-visible)
  - invoices.csv                 : overdue invoices, FK'd to customers (agent-visible)
  - ground_truth_HIDDEN.csv      : per-invoice, per-action response probabilities
                                    + importance-weighted annoyance penalty.
                                    Simulation engine only — agent must NOT read this.
"""

import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

fake = Faker()
random.seed(7)
Faker.seed(7)

N_CUSTOMERS = 40
N_INVOICES = 75
TODAY = datetime(2026, 3, 1)

INDUSTRIES = ["Manufacturing", "IT Services", "Retail", "Logistics",
              "Healthcare", "Construction", "F&B", "Textiles"]
CHANNELS = ["email", "whatsapp", "call"]
LANGUAGES = ["English", "Hinglish"]
ACTIONS = ["gentle_reminder", "firm_reminder", "phone_call",
           "payment_plan_offer", "escalate_collections"]

# ---------------------------------------------------------------------------
# 1. Customer master table
# ---------------------------------------------------------------------------

def make_customer(idx):
    annual_revenue = round(random.lognormvariate(15, 1.1), -3)
    payment_history_score = round(random.betavariate(2.5, 2), 3)

    if annual_revenue > 8_000_000:
        tier = "VIP"
    elif annual_revenue > 2_000_000:
        tier = "Standard"
    else:
        tier = "New"

    importance_score = round(min(1.0, annual_revenue / 12_000_000), 3)

    return {
        "customer_id": f"CUST{idx:04d}",
        "customer_name": fake.company(),
        "industry": random.choice(INDUSTRIES),
        "annual_revenue_inr": annual_revenue,
        "relationship_tier": tier,
        "importance_score": importance_score,
        "payment_history_score": payment_history_score,
        "preferred_channel": random.choice(CHANNELS),
        "language_pref": random.choices(LANGUAGES, weights=[0.6, 0.4])[0],
    }


customers = [make_customer(i) for i in range(1, N_CUSTOMERS + 1)]
df_customers = pd.DataFrame(customers)
customers_by_id = {c["customer_id"]: c for c in customers}

# ---------------------------------------------------------------------------
# 2. Invoices, FK'd to customers
# ---------------------------------------------------------------------------

def make_invoice(idx, customer):
    days_overdue = random.choice(
        [random.randint(1, 15)] * 3 +
        [random.randint(16, 45)] * 2 +
        [random.randint(46, 90)] * 1
    )
    invoice_date = TODAY - timedelta(days=days_overdue + random.randint(30, 60))
    due_date = TODAY - timedelta(days=days_overdue)
    amount = round(random.uniform(15000, 800000), 2)

    hist = customer["payment_history_score"]
    if hist > 0.7 and days_overdue < 20:
        risk_segment = "low"
    elif hist < 0.35 or days_overdue > 60:
        risk_segment = "high"
    else:
        risk_segment = "medium"

    return {
        "invoice_id": f"INV{idx:05d}",
        "customer_id": customer["customer_id"],
        "invoice_amount": amount,
        "invoice_date": invoice_date.strftime("%Y-%m-%d"),
        "due_date": due_date.strftime("%Y-%m-%d"),
        "days_overdue": days_overdue,
        "risk_segment": risk_segment,
        "prior_contact_count": 0,
        "status": "overdue",
    }


invoices = []
for i in range(1, N_INVOICES + 1):
    customer = random.choice(customers)
    invoices.append(make_invoice(i, customer))

df_invoices = pd.DataFrame(invoices)

# ---------------------------------------------------------------------------
# 3. Hidden response model — importance-weighted annoyance
# ---------------------------------------------------------------------------

def make_response_model(invoice, customer):
    base = customer["payment_history_score"]
    overdue_penalty = min(invoice["days_overdue"] / 90, 1.0) * 0.3
    importance = customer["importance_score"]

    action_strength = {
        "gentle_reminder": 0.15,
        "firm_reminder": 0.30,
        "phone_call": 0.45,
        "payment_plan_offer": 0.55,
        "escalate_collections": 0.70,
    }
    action_annoyance_base = {
        "gentle_reminder": 0.02,
        "firm_reminder": 0.05,
        "phone_call": 0.06,
        "payment_plan_offer": 0.03,
        "escalate_collections": 0.18,
    }

    rows = []
    for action, strength in action_strength.items():
        raw_prob = base * 0.5 + strength * 0.5 - overdue_penalty
        raw_prob = max(0.03, min(0.92, raw_prob + random.uniform(-0.05, 0.05)))

        pay_prob = round(raw_prob * 0.55, 3)
        promise_prob = round(raw_prob * 0.30, 3)
        partial_prob = round(raw_prob * 0.15, 3)
        ignore_prob = round(max(0.0, 1 - pay_prob - promise_prob - partial_prob), 3)

        importance_multiplier = 1 + importance * (2.5 if action == "escalate_collections" else 0.6)
        annoyance = round(action_annoyance_base[action] * importance_multiplier, 4)

        rows.append({
            "invoice_id": invoice["invoice_id"],
            "action": action,
            "pay_prob": pay_prob,
            "promise_prob": promise_prob,
            "partial_pay_prob": partial_prob,
            "ignore_prob": ignore_prob,
            "annoyance_penalty": annoyance,
        })
    return rows


response_rows = []
for inv in invoices:
    cust = customers_by_id[inv["customer_id"]]
    response_rows.extend(make_response_model(inv, cust))
df_response = pd.DataFrame(response_rows)

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

df_customers.to_csv("data/customers.csv", index=False)
df_invoices.to_csv("data/invoices.csv", index=False)
df_response.to_csv("data/ground_truth_HIDDEN.csv", index=False)

print(f"Customers generated: {len(df_customers)}")
print(df_customers["relationship_tier"].value_counts())
print(f"\nInvoices generated: {len(df_invoices)}")
print(f"Total overdue amount: INR {df_invoices['invoice_amount'].sum():,.2f}")
print(f"\nRisk segment breakdown:")
print(df_invoices["risk_segment"].value_counts())
print(f"\nHidden response-model rows: {len(df_response)}")
