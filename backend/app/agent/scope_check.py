from app.agent.gemini_client import generate_simple
#imports the function generate_simple from gemini_client.py

#Assign a role to the llm and it checks if the user's query is within the scope or out of the scope.
SCOPE_CHECK_PROMPT = """
You are a scope classifier for a retail seller's returns-analysis assistant.

The assistant's PURPOSE is to help sellers understand and act on product return data —
patterns, root causes, trends, comparisons, refund amounts, and recommendations tied to
their own store's returns, orders, SKUs, and customer feedback.

IN_SCOPE includes (non-exhaustive — reason by purpose, not exact wording):
- Return patterns, reasons, trends, and root causes
- Refund amounts and financial impact caused by returns
- Comparing return rates or return-related metrics across products or SKUs
- Customer feedback or ratings tied to product returns
- Order and delivery timing as it relates to return causes
- Return anomalies, spikes, or unusual patterns
- Return-related recommendations and seller insights

OUT_OF_SCOPE includes:
- General business metrics not tied to returns
  (total revenue, sales, profit margin, inventory levels,
   marketing performance, forecasting, warehouse operations)
- Requests about other sellers' data
- Industry-wide statistics not derived from the authenticated seller's data
- General knowledge questions
- Coding help
- Personal advice
- Entertainment, sports, politics, weather, or unrelated topics

The distinguishing test:

If the query can reasonably be answered using return records,
refund data, SKU return data, order-return correlations,
customer feedback, or return-related analytics,
classify it as IN_SCOPE.

If answering the query would require information outside those domains,
classify it as OUT_OF_SCOPE.

Respond with EXACTLY ONE WORD:

IN_SCOPE

or

OUT_OF_SCOPE

User query:
{query}
"""

def check_scope(query: str) -> dict:
    """
    Classifies whether a query is within the
    Retail Return Reasoning Agent's scope.

    Returns:
    --------
    {
        "allowed": bool,
        "classification": str,
        "message": str
    }
    """

    # Reject empty queries
    if not query or not query.strip(): #query.strip() removes extra spaces;this line checks if its an empty query
        return {
            "allowed": False, #do not continue
            "classification": "OUT_OF_SCOPE",
            "message": (
                "Please enter a question related to product returns, "
                "return reasons, customer feedback, return trends, "
                "SKU analysis, product comparisons, or return anomalies."
            )
        }

    try:
        prompt = SCOPE_CHECK_PROMPT.format(
            query=query.strip()
        ) #pass this to User Query in SCOPE_CHECK_PROMPT [THE BIG PROMPT]
        #print(prompt) would print entire user query+the big prompt
        response = generate_simple(prompt)
        #gemini receives the prompt--thinks--and returns in_scope or out_of_scope
        result = response.strip().upper()#either IN_SCOPE or OUT_OF_SCOPE
        # Only accept an exact IN_SCOPE.
        # Everything else is rejected.
        if result == "IN_SCOPE":
            return {
                "allowed": True,
                "classification": "IN_SCOPE",
                "message": ""
            } #continue to tool calling

        return {
            "allowed": False, #Fail Closed
            "classification": "OUT_OF_SCOPE",
            "message": (
                "I can only assist with return-related analysis, including "
                "return reasons, return trends, refund impact, customer feedback, "
                "SKU return analysis, product comparisons, delivery-return correlations, "
                "and anomaly detection."
            )
        }

    except Exception: #built in python class to catch any general errors
        # Fail closed.
        # Better to reject than risk hallucination.
        return {
            "allowed": False,
            "classification": "OUT_OF_SCOPE",
            "message": (
                "Unable to verify whether the request falls within the "
                "assistant's supported return-analysis scope."
            )
        }