"""
Synthetic B2B receivables (dunning) dataset generator.

Produces:
  - invoices.csv               : what the agent can see
  - ground_truth_HIDDEN.csv    : per-invoice, per-action response probabilities
                                  used ONLY by the simulation engine (Day 3+),
                                  never by the agent's decision logic.

The agent's job: for each overdue invoice, choose an action (or wait), subject
to compliance rules and stopping rules, to maximize recovered amount without
over-contacting customers (which the hidden model penalizes).
"""

import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

fake = Faker()
random.seed(7)
Faker.seed(7)

N_INVOICES = 75
TODAY = datetime(2026, 3, 1)  # simulation "current date"

INDUSTRIES = ["Manufacturing", "IT Services", "Retail", "Logistics",
              "Healthcare", "Construction", "F&B", "Textiles"]

ACTIONS = ["gentle_reminder", "firm_reminder", "phone_call",
           "payment_plan_offer", "escalate_collections"]

CHANNELS = ["email", "whatsapp", "call"]
LANGUAGES = ["English", "Hinglish"]

RISK_SEGMENTS = ["low", "medium", "high"]


def make_invoice(idx):
    days_overdue = random.choice(
        [random.randint(1, 15)] * 3 +      # weighted toward early-overdue
        [random.randint(16, 45)] * 2 +
        [random.randint(46, 90)] * 1
    )
    invoice_date = TODAY - timedelta(days=days_overdue + random.randint(30, 60))
    due_date = TODAY - timedelta(days=days_overdue)
    amount = round(random.uniform(15000, 800000), 2)  # INR, B2B scale

    # payment_history_score: 0 = always late/defaults, 1 = always pays on time
    payment_history_score = round(random.betavariate(2.5, 2), 3)

    if payment_history_score > 0.7 and days_overdue < 20:
        risk_segment = "low"
    elif payment_history_score < 0.35 or days_overdue > 60:
        risk_segment = "high"
    else:
        risk_segment = "medium"

    return {
        "invoice_id": f"INV{idx:05d}",
        "customer_id": f"CUST{(idx % 40):04d}",  # some repeat customers
        "customer_name": fake.company(),
        "industry": random.choice(INDUSTRIES),
        "invoice_amount": amount,
        "invoice_date": invoice_date.strftime("%Y-%m-%d"),
        "due_date": due_date.strftime("%Y-%m-%d"),
        "days_overdue": days_overdue,
        "payment_history_score": payment_history_score,
        "risk_segment": risk_segment,
        "prior_contact_count": 0,  # agent updates this during simulation
        "contact_email": fake.company_email(),
        "preferred_channel": random.choice(CHANNELS),
        "language_pref": random.choices(LANGUAGES, weights=[0.6, 0.4])[0],
        "status": "overdue",
    }


def make_response_model(invoice):
    """
    Hidden ground-truth response probabilities per action for this invoice.
    Higher payment_history_score -> generally more responsive.
    Higher days_overdue -> lower baseline willingness, needs stronger action.
    escalate_collections has higher pay-probability but higher relationship
    damage (annoyance) -- forces agents to not jump straight to it.
    """
    base = invoice["payment_history_score"]
    overdue_penalty = min(invoice["days_overdue"] / 90, 1.0) * 0.3

    action_strength = {
        "gentle_reminder": 0.15,
        "firm_reminder": 0.30,
        "phone_call": 0.45,
        "payment_plan_offer": 0.55,
        "escalate_collections": 0.70,
    }
    action_annoyance = {
        "gentle_reminder": 0.02,
        "firm_reminder": 0.05,
        "phone_call": 0.06,
        "payment_plan_offer": 0.03,   # customers appreciate flexibility
        "escalate_collections": 0.18,  # damages relationship most
    }

    rows = []
    for action, strength in action_strength.items():
        raw_prob = base * 0.5 + strength * 0.5 - overdue_penalty
        raw_prob = max(0.03, min(0.92, raw_prob + random.uniform(-0.05, 0.05)))

        pay_prob = round(raw_prob * 0.55, 3)
        promise_prob = round(raw_prob * 0.30, 3)
        partial_prob = round(raw_prob * 0.15, 3)
        ignore_prob = round(max(0.0, 1 - pay_prob - promise_prob - partial_prob), 3)

        rows.append({
            "invoice_id": invoice["invoice_id"],
            "action": action,
            "pay_prob": pay_prob,
            "promise_prob": promise_prob,
            "partial_pay_prob": partial_prob,
            "ignore_prob": ignore_prob,
            "annoyance_penalty": action_annoyance[action],
        })
    return rows


invoices = [make_invoice(i) for i in range(1, N_INVOICES + 1)]
df_invoices = pd.DataFrame(invoices)

response_rows = []
for inv in invoices:
    response_rows.extend(make_response_model(inv))
df_response = pd.DataFrame(response_rows)

df_invoices.to_csv("data/invoices.csv", index=False)
df_response.to_csv("data/ground_truth_HIDDEN.csv", index=False)

print(f"Invoices generated: {len(df_invoices)}")
print(f"Total overdue amount: INR {df_invoices['invoice_amount'].sum():,.2f}")
print(f"\nRisk segment breakdown:")
print(df_invoices["risk_segment"].value_counts())
print(f"\nHidden response-model rows: {len(df_response)} (75 invoices x 5 actions)")
