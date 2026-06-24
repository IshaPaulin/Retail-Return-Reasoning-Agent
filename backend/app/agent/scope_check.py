from app.agent.gemini_client import generate_simple


# =====================================================
# GREETINGS
# =====================================================

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "greetings"
}


# =====================================================
# BOUNDARY CLASSIFIER PROMPT
# =====================================================

SCOPE_CHECK_PROMPT = """
SYSTEM ROLE

You are a Security and Boundary Enforcement Classifier for a Retail Return Reasoning Agent.

You are NOT a chatbot.
You are NOT a data analyst.
You are NOT allowed to answer the user's question.

Your ONLY responsibility is to determine whether the user's request
falls within the assistant's authorized operating boundary.

--------------------------------------------------
AUTHORIZED DATA BOUNDARY
--------------------------------------------------

The assistant may access and reason about:

AUTHENTICATED SELLER DATA:
- Product return records
- Return reasons
- Return trends
- Return root-cause analysis
- Refund amounts caused by returns
- Return-related financial impact
- Customer feedback related to returns
- SKU-level return analysis
- Product comparisons based on return metrics
- Order-delivery issues related to returns
- Return anomalies and unusual patterns

PUBLIC BENCHMARK DATA (when available through authorized sources):
- Industry return-rate benchmarks
- Sector-level return averages
- Marketplace-wide return statistics
- Public retail return studies and trends

The assistant may generate recommendations ONLY when they are
grounded in authorized data sources.

--------------------------------------------------
UNAUTHORIZED DATA BOUNDARY
--------------------------------------------------

The assistant must NOT answer questions requiring:

Business Analytics Unrelated to Returns:
- Total revenue
- Total sales
- Profit margins
- Inventory levels
- Marketing performance
- Forecasting
- Warehouse operations

Private or Restricted Data:
- Other sellers' private data
- Competitor proprietary information
- Confidential marketplace data
- Internal company information not available through authorized sources

General Knowledge:
- Coding help
- Mathematics
- Science
- Politics
- Weather
- Sports
- Entertainment
- Personal advice
- Any topic unrelated to retail returns

--------------------------------------------------
DECISION POLICY
--------------------------------------------------

Classify as IN_SCOPE only if ALL conditions are true:

1. The request is related to returns, refunds, return trends,
   return causes, return-related customer feedback,
   return-related financial impact, SKU return analysis,
   product return comparisons, delivery-return correlations,
   or return anomalies.

2. The request can be answered using:
   - authenticated seller return-related data, OR
   - authorized public benchmark data.

3. No private, unauthorized, competitor-specific,
   or unrelated information is required.

Otherwise classify as OUT_OF_SCOPE.

--------------------------------------------------
OUTPUT POLICY
--------------------------------------------------

Return EXACTLY ONE WORD:

IN_SCOPE

or

OUT_OF_SCOPE

Do not explain.
Do not provide reasoning.
Do not answer the question.

User Query:
{query}
"""


# =====================================================
# MAIN FUNCTION
# =====================================================

def check_scope(query: str) -> dict:
    """
    Determines whether a query falls within the
    Retail Return Reasoning Agent's authorized boundary.

    Returns:
    {
        "allowed": bool,
        "classification": str,
        "message": str
    }
    """

    # ----------------------------------
    # Empty Query
    # ----------------------------------

    if not query or not query.strip():
        return {
            "allowed": False,
            "classification": "OUT_OF_SCOPE",
            "message": (
                "Please enter a return-related question."
            )
        }

    query_clean = query.strip()
    query_lower = query_clean.lower()

    # ----------------------------------
    # Greeting Detection
    # ----------------------------------

    if query_lower in GREETINGS:
        return {
            "allowed": False,
            "classification": "GREETING",
            "message": (
                "Hello! I can help you analyze return reasons, "
                "return trends, customer feedback, refund impact, "
                "SKU performance, product comparisons, and return anomalies."
            )
        }

    # ----------------------------------
    # Boundary Classification
    # ----------------------------------

    try:

        prompt = SCOPE_CHECK_PROMPT.format(
            query=query_clean
        )

        response = generate_simple(prompt)

        classification = response.strip().upper()

        # Fail Closed
        if classification == "IN_SCOPE":
            return {
                "allowed": True,
                "classification": "IN_SCOPE",
                "message": ""
            }

        return {
            "allowed": False,
            "classification": "OUT_OF_SCOPE",
            "message": (
                "I can only assist with return-related analysis "
                "for your store, including return reasons, return trends, "
                "refund impact, customer feedback, SKU analysis, "
                "product comparisons, delivery-return correlations, "
                "return anomalies, and benchmark comparisons."
            )
        }

    except Exception:

        return {
            "allowed": False,
            "classification": "OUT_OF_SCOPE",
            "message": (
                "Unable to verify whether the request falls "
                "within the assistant's authorized scope."
            )
        }