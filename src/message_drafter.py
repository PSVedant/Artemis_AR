"""
Message drafting layer for Artemis_AR.

Given an action already chosen by the policy engine (gentle_reminder,
firm_reminder, phone_call, payment_plan_offer, escalate_collections), draft
the actual customer-facing message in English or Hinglish.

Design principles:
  - COMPLIANCE-BOUNDED: the LLM is constrained by a system prompt that
    forbids coercive/threatening language and requires factual-only
    content (invoice_id, amount, due date). Tone intensifies with action
    tier but never crosses into threats.
  - GRACEFUL FAILURE: if the LLM call fails for any reason (no API key,
    network issue, rate limit), this falls back to a pre-written template
    automatically. The invoice still gets a usable message; the failure
    is logged, not hidden. This satisfies the "handle one failure
    gracefully" requirement from the brief.
  - The policy engine already decided WHAT to do; this module only decides
    HOW to say it. It never changes the action itself.
"""

import os
from dataclasses import dataclass
from typing import Optional

COMPLIANCE_SYSTEM_PROMPT = """You are drafting a payment reminder message for a B2B accounts receivable team.

STRICT RULES you must follow:
1. State only factual information: invoice ID, amount owed, due date, days overdue.
2. NEVER use threatening, coercive, or intimidating language.
3. NEVER imply legal action unless the action tier is explicitly "escalate_collections" -- and even then, state only that "the account will be referred to our collections process" (factual), never threaten specific legal consequences, lawsuits, or credit damage.
4. Tone must scale naturally with the action tier:
   - gentle_reminder: friendly, assumes oversight, no urgency language
   - firm_reminder: direct, clear deadline, still professional and respectful
   - phone_call: this is a call script/talking points, not an email -- conversational, allow room for the customer to explain
   - payment_plan_offer: helpful, solution-oriented, emphasize flexibility
   - escalate_collections: serious and formal, but factual and free of threats
5. Never use insulting, humiliating, or personally critical language about the customer or their business.
6. Keep it concise -- 3-5 sentences for written messages.
7. If language is Hinglish, write natural code-mixed Hindi-English as commonly used in Indian business communication -- not a literal translation, not overly formal Hindi.
"""

TEMPLATE_FALLBACKS = {
    ("gentle_reminder", "English"):
        "Hi {customer_name}, hope you're doing well. Just a quick note that invoice "
        "{invoice_id} for INR {amount:,.2f} was due on {due_date}. If you've already "
        "paid, please disregard this message. Otherwise, please let us know if you "
        "need anything from our side to process this. Thanks!",

    ("gentle_reminder", "Hinglish"):
        "Hi {customer_name}, umeed hai aap theek honge. Bas ek reminder ki invoice "
        "{invoice_id} (INR {amount:,.2f}) ki due date {due_date} thi. Agar payment "
        "already ho chuki hai to please ignore this message. Kuch bhi chahiye ho "
        "hamari taraf se to batayein. Thanks!",

    ("firm_reminder", "English"):
        "Dear {customer_name}, invoice {invoice_id} for INR {amount:,.2f} is now "
        "{days_overdue} days past its due date of {due_date}. Please arrange payment "
        "at your earliest convenience, or reach out if there's an issue we can help "
        "resolve. We'd appreciate a response by end of week.",

    ("firm_reminder", "Hinglish"):
        "Dear {customer_name}, invoice {invoice_id} (INR {amount:,.2f}) ab "
        "{days_overdue} din se overdue hai, due date {due_date} thi. Please jaldi "
        "payment arrange karein, ya agar koi issue hai to hamein batayein, hum help "
        "kar sakte hain. Is week ke andar response ki ummeed rahegi.",

    ("phone_call", "English"):
        "[Call script] Greet {customer_name} warmly. Reference invoice {invoice_id}, "
        "INR {amount:,.2f}, {days_overdue} days overdue. Ask if there's a reason for "
        "the delay. Listen for any dispute or cash-flow issue. Offer to discuss a "
        "payment plan if needed. Confirm a specific date for payment or next contact "
        "before ending the call.",

    ("phone_call", "Hinglish"):
        "[Call script] {customer_name} ko warmly greet karein. Invoice {invoice_id}, "
        "INR {amount:,.2f}, {days_overdue} din overdue ka reference dein. Poochein "
        "ki delay ki koi wajah hai kya. Agar dispute ya cash-flow issue hai to sunein. "
        "Zaroorat ho to payment plan discuss karne ki offer karein. Call khatam karne "
        "se pehle ek specific date confirm karein.",

    ("payment_plan_offer", "English"):
        "Dear {customer_name}, we understand cash flow can be tight. For invoice "
        "{invoice_id} (INR {amount:,.2f}, {days_overdue} days overdue), we're happy "
        "to work out a payment plan in installments if that helps. Please let us "
        "know a schedule that works for you, and we'll confirm the details.",

    ("payment_plan_offer", "Hinglish"):
        "Dear {customer_name}, hum samajhte hain cash flow kabhi tight ho sakta hai. "
        "Invoice {invoice_id} (INR {amount:,.2f}, {days_overdue} din overdue) ke liye, "
        "hum installments mein payment plan bhi arrange kar sakte hain agar wo help "
        "kare. Please batayein kaunsa schedule aapke liye theek rahega.",

    ("escalate_collections", "English"):
        "Dear {customer_name}, despite previous reminders, invoice {invoice_id} "
        "(INR {amount:,.2f}) remains unpaid, now {days_overdue} days overdue. If "
        "payment or a satisfactory response is not received within 7 days, this "
        "account will be referred to our collections process. We would still "
        "welcome the opportunity to resolve this directly before that becomes "
        "necessary.",

    ("escalate_collections", "Hinglish"):
        "Dear {customer_name}, pichle reminders ke bawajood, invoice {invoice_id} "
        "(INR {amount:,.2f}) abhi tak unpaid hai, {days_overdue} din overdue. Agar 7 "
        "din ke andar payment ya satisfactory response nahi milta, to yeh account "
        "collections process mein bhej diya jayega. Hum abhi bhi directly isse "
        "resolve karna prefer karenge.",
}


@dataclass
class DraftedMessage:
    invoice_id: str
    action: str
    language: str
    text: str
    source: str  # "llm" or "template_fallback"
    fallback_reason: Optional[str] = None


def _template_fallback(invoice_id, action, language, customer_name, amount, due_date, days_overdue, reason=None):
    key = (action, language)
    if key not in TEMPLATE_FALLBACKS:
        key = (action, "English")  # last-resort fallback
    text = TEMPLATE_FALLBACKS[key].format(
        customer_name=customer_name, invoice_id=invoice_id, amount=amount,
        due_date=due_date, days_overdue=days_overdue,
    )
    return DraftedMessage(invoice_id, action, language, text, "template_fallback", reason)


def draft_message(invoice_id, action, language, customer_name, amount, due_date,
                   days_overdue, use_llm=True) -> DraftedMessage:
    """
    Attempt an LLM-drafted message under compliance constraints. Falls back
    to a template automatically and gracefully on any failure.

    Provider is chosen via the LLM_PROVIDER env var: "anthropic" (default,
    requires ANTHROPIC_API_KEY, paid) or "groq" (requires GROQ_API_KEY,
    free tier, no credit card). This lets the project be architected for
    the Anthropic API in production while using a free provider for local
    development and demos, without changing any calling code.
    """
    if not use_llm:
        return _template_fallback(invoice_id, action, language, customer_name,
                                   amount, due_date, days_overdue, reason="LLM disabled by caller")

    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    user_prompt = (
        f"Draft a {action.replace('_', ' ')} message in {language} for:\n"
        f"Customer: {customer_name}\n"
        f"Invoice: {invoice_id}\n"
        f"Amount: INR {amount:,.2f}\n"
        f"Due date: {due_date}\n"
        f"Days overdue: {days_overdue}\n\n"
        f"Output ONLY the message text, no preamble."
    )

    if provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return _template_fallback(invoice_id, action, language, customer_name,
                                       amount, due_date, days_overdue,
                                       reason="GROQ_API_KEY not set")
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

            response = client.chat.completions.create(
                model=model,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": COMPLIANCE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = response.choices[0].message.content.strip()
            if not text:
                raise ValueError("Empty response from LLM")
            return DraftedMessage(invoice_id, action, language, text, "llm")

        except Exception as e:
            return _template_fallback(invoice_id, action, language, customer_name,
                                       amount, due_date, days_overdue,
                                       reason=f"Groq call failed: {type(e).__name__}: {e}")

    # default: anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _template_fallback(invoice_id, action, language, customer_name,
                                   amount, due_date, days_overdue,
                                   reason="ANTHROPIC_API_KEY not set")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=COMPLIANCE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(block.text for block in response.content if hasattr(block, "text")).strip()

        if not text:
            raise ValueError("Empty response from LLM")

        return DraftedMessage(invoice_id, action, language, text, "llm")

    except Exception as e:
        # graceful failure: log the reason, fall back, never crash the pipeline
        return _template_fallback(invoice_id, action, language, customer_name,
                                   amount, due_date, days_overdue,
                                   reason=f"LLM call failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    # smoke test -- will fall back to template since no API key is set here
    msg = draft_message(
        invoice_id="INV00042", action="firm_reminder", language="Hinglish",
        customer_name="Sharma Textiles Pvt Ltd", amount=145000.0,
        due_date="2026-02-15", days_overdue=25,
    )
    print(f"Source: {msg.source}")
    if msg.fallback_reason:
        print(f"Fallback reason: {msg.fallback_reason}")
    print(f"\n{msg.text}")
