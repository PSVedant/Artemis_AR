# Artemis_AR

**B2B receivables recovery agent — bounded, gated, and honest about what it can and can't prove.**

Built for Razorpay Hackathon, Track 03: AI Revenue Recovery.

---

## What this is

A dunning (payment-reminder) agent for overdue B2B invoices. Given a batch of overdue receivables, it decides the right escalation action per invoice — from a gentle reminder up to collections referral — subject to explicit compliance rules and a **real, blocking human-approval gate** before any high-stakes action fires. Every decision, message, and outcome is logged to an audit trail. Every invoice it can't resolve is reported honestly, not hidden.

**What it is not:** a fraud detector, a live Razorpay integration, or a system trained on real customer response data. Read the [Limitations](#honest-limitations) section before assuming otherwise — this README is written to survive a skeptical read, not to oversell.

---

## The core idea

Most "AI agent" demos either (a) always act, with no way to stop them, or (b) never really act, staying purely advisory. Neither is what a finance team would actually deploy. Artemis_AR does three things a real deployment would require:

1. **Bounded** — a policy engine with externally configured, justified thresholds (cooldown days, max attempts, escalation gates), not a black box.
2. **Gated** — before any escalation to collections on an important customer, the agent stops completely. No outcome is sampled, no action executes, until a human explicitly approves or denies it.
3. **Honest** — every invoice that couldn't be resolved shows up in an exception report with a real reason. Nothing is silently written off.

---

## Architecture

```
generate_data.py          → synthetic invoices, customers, hidden response model
        ↓
policy_engine.py           → decides next action per invoice (config-driven, gated)
        ↓
simulation_engine.py       → runs the policy against the hidden response model
        ↓
run_gated_simulation.py    → Phase 1: pauses on any action needing human approval
        ↓
resolve_approvals.py       → Phase 2: YOU approve/deny each real pending case
        ↓
build_final_audit_trail.py → merges real decisions with LLM-drafted messages
        ↓
api.py (FastAPI)            → serves the real data, read-only
        ↓
dashboard.html               → visualizes it
```

**Why hidden ground truth:** the policy engine never sees the response-probability model that determines whether a customer pays, ignores, or promises. Only the simulation environment does. This mirrors real train/test separation — the agent can't "cheat" by knowing outcomes in advance.

---

## Setup

```powershell
# 1. Environment
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install pandas faker numpy fastapi uvicorn groq anthropic

# 2. Generate the synthetic dataset (75 invoices, 40 customers)
python scripts/generate_data.py

# 3. Verify the policy engine (10 assertions)
python test_day2.py

# 4. Run the gated simulation — this WILL pause and wait for you
python -m src.run_gated_simulation
python -m src.resolve_approvals
# ^ repeat resolve_approvals.py until it reports 0 pending

# 5. Build the final audit trail (drafts real messages; set LLM_PROVIDER=groq
#    and GROQ_API_KEY for a free-tier LLM, or it gracefully falls back to templates)
python -m src.build_final_audit_trail
python -m src.exception_report

# 6. Start the backend
uvicorn src.api:app --port 8000

# 7. Open the dashboard
# just open frontend/dashboard.html in a browser
```

---

## Results (from an actual run — not illustrative)

| Metric | Smart policy | Naive fixed-ladder baseline |
|---|---|---|
| Recovery rate | 74.2% | ~69.9%* |
| Invoices exhausted (unresolved) | 20 | 23 |
| Escalations on important customers | Every one logged + human-approved | Fires unchecked (once given equal attempt budget — see note below) |

*\*The baseline number required a controlled follow-up experiment. In the first comparison run, the baseline's fixed one-tier-per-contact ladder never structurally reached the collections-escalation tier before hitting the shared attempt cap — meaning it looked "safer" only because it never got the chance to be otherwise, not because it exercised any real restraint. A second, symmetric run with a relaxed cap confirmed this: under equal conditions, the baseline escalates on important customers with zero checks, while the smart policy routes every equivalent decision through a logged approval step. This distinction — and the fact that the first comparison was misleading and had to be corrected — is documented in `src/compare_policies.py` and is, honestly, one of the more interesting parts of building this.*

---

## Honest limitations


- **The hidden response model is self-designed, not empirical.** The probabilities governing whether a customer pays, ignores, or promises were written by me to be *plausible*, not fitted to real collections data. "74.2% recovery" demonstrates the mechanism works — it is not a validated prediction of real-world performance. Anyone claiming otherwise about a system like this should be doubted.
- **No live Razorpay integration.** This track is scored partly on platform usage; this submission is a self-contained simulation with no test-mode API calls. That's a real gap, not a stylistic choice — noting it here rather than hoping it goes unnoticed.
- **Small, clean synthetic scale.** 75 invoices, 40 customers, deliberately engineered edge cases. Not tested at volume or against messy real-world data.
- **The dashboard is read-only.** The genuinely novel part of this system — the human-in-the-loop gate — only exists in the CLI (`resolve_approvals.py`). It is not (yet) interactive in the web UI. If demoing live, show the CLI moment; don't rely on the dashboard to carry that story.
- **No persisted test suite beyond the policy engine.** `test_day2.py` has 10 real assertions on the decision logic. The simulation engine, message drafter, and API were verified interactively during development, not committed as an automated suite.

---


## Project structure

```
Artemis_AR/
├── data/                  # generated datasets, audit trails, reports (gitignored: none — all real, kept for reproducibility)
├── scripts/
│   └── generate_data.py
├── config/
│   └── policy.json        # every threshold, with a written justification
├── src/
│   ├── policy_engine.py
│   ├── baseline_policy.py
│   ├── simulation_engine.py
│   ├── state_io.py
│   ├── run_gated_simulation.py
│   ├── resolve_approvals.py
│   ├── message_drafter.py
│   ├── build_final_audit_trail.py
│   ├── exception_report.py
│   ├── compare_policies.py
│   └── api.py
├── frontend/
│   └── dashboard.html
├── test_day2.py
└── README.md
```