import re
from app.agent.gemini_client import generate_simple

_OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")

GREETINGS = {
    "hi", "hello", "hey", "good morning", "good afternoon",
    "good evening", "greetings", "thanks", "thank you", "okay", "ok"
}

SCOPE_CHECK_PROMPT = """
You are a scope classifier for a Retail Return Reasoning Agent.

The agent helps sellers understand product returns. It can answer questions about:
- Return records, return rates, return reasons, return trends
- Customer feedback and ratings related to returns
- SKU and variant-level return analysis
- Anomalies and spikes in return behaviour
- Delivery and order issues correlated with returns
- Comparing return performance across products

CLASSIFICATION RULES:

Mark as IN_SCOPE if ANY of these are true:
- The message mentions a product name (even without explicitly saying "return")
- The message is a follow-up to a return-related conversation (e.g. a product name, an ID, "yes", "tell me more")
- The message asks about returns, reasons, feedback, SKUs, anomalies, trends, or delivery
- The message is ambiguous but could plausibly be about returns

Mark as OUT_OF_SCOPE only if the message is CLEARLY unrelated to retail or returns:
- General knowledge (weather, sports, news, cooking, coding, science)
- Personal advice, jokes, creative writing
- Questions about other sellers or competitors
- Financial advice, legal advice, medical questions

When in doubt, mark as IN_SCOPE. It is better to attempt a helpful response
than to incorrectly refuse a legitimate seller question.

Respond with exactly one word: IN_SCOPE or OUT_OF_SCOPE

User message: {query}
"""


def check_scope(query: str) -> dict:
    if not query or not query.strip():
        return {
            "allowed": False,
            "classification": "OUT_OF_SCOPE",
            "message": "Please enter a question about your products or returns.",
        }

    query_clean = query.strip()
    query_lower = query_clean.lower()

    # Greetings — handle directly without Gemini
    if query_lower in GREETINGS:
        return {
            "allowed": False,
            "classification": "GREETING",
            "message": (
                "Hello! I can help you analyze return reasons, "
                "return trends, customer feedback, refund impact, "
                "SKU performance, product comparisons, and return anomalies."
            ),
        }

    # Raw ObjectId — always a follow-up, always allow
    if _OBJECT_ID_RE.fullmatch(query_clean):
        return {"allowed": True, "classification": "IN_SCOPE", "message": ""}

    # Short messages (under 6 words) are almost always follow-ups — allow them
    if len(query_clean.split()) <= 6:
        return {"allowed": True, "classification": "IN_SCOPE", "message": ""}

    # Gemini classification for longer queries
    try:
        prompt = SCOPE_CHECK_PROMPT.format(query=query_clean)
        response = generate_simple(prompt)
        classification = response.strip().upper()

        if classification == "IN_SCOPE":
            return {"allowed": True, "classification": "IN_SCOPE", "message": ""}

        return {
            "allowed": False,
            "classification": "OUT_OF_SCOPE",
            "message": (
                "I can only assist with return-related analysis for your store — "
                "return reasons, trends, refund impact, customer feedback, "
                "SKU analysis, product comparisons, delivery correlations, and anomalies."
            ),
        }

    except Exception as e:
        # Fail open — don't block the user because of a Gemini API failure
        print(f"[SCOPE CHECK ERROR] {type(e).__name__}: {e}")
        return {"allowed": True, "classification": "IN_SCOPE", "message": ""}