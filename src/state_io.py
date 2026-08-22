"""
Persist InvoiceState objects to disk between the gated simulation run
(Phase 1) and the approval-resolution CLI (Phase 2/3), which run as
separate processes. Everything serialized here is real simulation state --
no fabricated fields.
"""

import json
from datetime import date

from src.policy_engine import InvoiceState


def _date_to_str(d):
    return d.isoformat() if d else None


def _str_to_date(s):
    return date.fromisoformat(s) if s else None


def serialize_states(states: dict) -> str:
    out = {}
    for inv_id, s in states.items():
        out[inv_id] = {
            "invoice_id": s.invoice_id,
            "customer_id": s.customer_id,
            "days_overdue": s.days_overdue,
            "risk_segment": s.risk_segment,
            "importance_score": s.importance_score,
            "status": s.status,
            "prior_contact_count": s.prior_contact_count,
            "last_contact_date": _date_to_str(s.last_contact_date),
            "action_history": s.action_history,
            "original_amount": s.original_amount,
            "remaining_amount": s.remaining_amount,
            "promise_date": _date_to_str(s.promise_date),
            "fatigue": s.fatigue,
            "pending_action": s.pending_action,
            "pending_reason": s.pending_reason,
            "pending_since_day": s.pending_since_day,
        }
    return json.dumps(out, indent=2)


def deserialize_states(json_str: str) -> dict:
    data = json.loads(json_str)
    states = {}
    for inv_id, d in data.items():
        states[inv_id] = InvoiceState(
            invoice_id=d["invoice_id"],
            customer_id=d["customer_id"],
            days_overdue=d["days_overdue"],
            risk_segment=d["risk_segment"],
            importance_score=d["importance_score"],
            status=d["status"],
            prior_contact_count=d["prior_contact_count"],
            last_contact_date=_str_to_date(d["last_contact_date"]),
            action_history=[tuple(x) for x in d["action_history"]],
            original_amount=d["original_amount"],
            remaining_amount=d["remaining_amount"],
            promise_date=_str_to_date(d["promise_date"]),
            fatigue=d["fatigue"],
            pending_action=d.get("pending_action"),
            pending_reason=d.get("pending_reason"),
            pending_since_day=d.get("pending_since_day"),
        )
    return states


def save_states(states: dict, path):
    with open(path, "w") as f:
        f.write(serialize_states(states))


def load_states_from_file(path) -> dict:
    with open(path) as f:
        return deserialize_states(f.read())
