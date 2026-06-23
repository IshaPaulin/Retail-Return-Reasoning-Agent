# app/agent/chatbot_pipeline.py

from langgraph.graph import StateGraph, END
from langgraph.graph.message import MessagesState
from langgraph.checkpoint.mongodb import MongoDBSaver
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import FLOOR_THRESHOLD, CEILING_THRESHOLD, MAX_ATTEMPTS
from app.database.connection import db, client
from app.agent.scope_check import check_scope
from app.agent.gemini_client import generate_with_tools, generate_simple
from app.agent.response_scorer import score_response
from app.tools import (
    get_product_return_data,
    get_return_reasons_breakdown,
    get_customer_feedback,
    get_return_trend,
    get_order_delivery_data,
    compare_seller_products,
    detect_anomalies,
    get_sku_return_breakdown,
)
from app.agent.tool_schemas import ALL_TOOL_SCHEMAS

# ---------------------------------------------------------------------------
# TOOL REGISTRY
# Maps tool name strings (what Gemini returns) to actual Python functions.
# seller_id is always injected from state — never from Gemini's arguments.
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "get_product_return_data": get_product_return_data,
    "get_return_reasons_breakdown": get_return_reasons_breakdown,
    "get_customer_feedback": get_customer_feedback,
    "get_return_trend": get_return_trend,
    "get_order_delivery_data": get_order_delivery_data,
    "compare_seller_products": compare_seller_products,
    "detect_anomalies": detect_anomalies,
    "get_sku_return_breakdown": get_sku_return_breakdown,
}


# ---------------------------------------------------------------------------
# STATE DEFINITION
# ---------------------------------------------------------------------------

class AgentState(MessagesState):
    seller_id: str
    scope_passed: bool = True   


# ---------------------------------------------------------------------------
# NODE 1: SCOPE CHECK
# Unchanged from original design.
# ---------------------------------------------------------------------------

def scope_check_node(state: AgentState) -> dict:
    user_message = next(
        (m.content for m in state["messages"]
         if isinstance(m, HumanMessage)), ""
    )

    scope_result = check_scope(user_message)
    if not scope_result["allowed"]:
        return {
            "messages": [AIMessage(content=scope_result["message"])],
            "scope_passed": False,
        }
    return {"scope_passed": True}


def scope_check_router(state: AgentState) -> str:
    if not state.get("scope_passed", True):
        return END
    return "agent"


# ---------------------------------------------------------------------------
# NODE 2: AGENT NODE
# Unchanged from original design.
# ---------------------------------------------------------------------------


def agent_node(state: AgentState) -> dict:
    response = generate_with_tools(state["messages"], ALL_TOOL_SCHEMAS)

    candidate = response.candidates[0]
    parts = candidate.content.parts if candidate.content and candidate.content.parts else []

    tool_calls = []
    text_parts = []

    for part in parts:
        if part.function_call:
            tool_calls.append({
                "name": part.function_call.name,
                "args": dict(part.function_call.args),
                "id":   part.function_call.name,
            })
        elif part.text:
            text_parts.append(part.text)

    return {"messages": [AIMessage(
        content="".join(text_parts),
        tool_calls=tool_calls,
    )]}


def agent_router(state: AgentState) -> str:
    last_message = state["messages"][-1]
    # If Gemini returned a function call, go to tool node
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    # If Gemini returned final text, go to scorer
    return "scorer"


# ---------------------------------------------------------------------------
# NODE 3: TOOL EXECUTION NODE
# Unchanged from original design.
# seller_id always injected from state — overrides anything Gemini passed.
# ---------------------------------------------------------------------------

def tool_node(state: AgentState) -> dict:
    seller_id = state["seller_id"]
    last_message = state["messages"][-1]
    tool_results = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        try:
            if tool_name not in TOOL_REGISTRY:
                raise KeyError(f"Unknown tool: {tool_name}")

            # Always inject seller_id from state, never from Gemini
            tool_args["seller_id"] = seller_id

            result = TOOL_REGISTRY[tool_name](**tool_args)

        except KeyError as e:
            result = {"error": f"Unknown tool requested: {str(e)}"}
        except TypeError as e:
            result = {
                "error": f"Invalid arguments for tool {tool_name}: {str(e)}"}
        except Exception as e:
            result = {
                "error": f"Tool execution failed for {tool_name}: {str(e)}"}

        tool_results.append(
            ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
                name=tool_name, 
            )
        )

    return {"messages": tool_results}


# ---------------------------------------------------------------------------
# NODE 4: SCORER NODE
# This is the node that changed. Full logic described below.
#
# - MAX_ATTEMPTS = 3 (1 original + 2 retries)
# - CEILING_THRESHOLD = 0.7 → serve immediately if hit
# - FLOOR_THRESHOLD = 0.4 → minimum trust level to serve cleanly
# - Any score below ceiling triggers retry (not just scores in 0.4–0.7)
# - Best-of-N selected after loop exhausts
# - If best < floor → serve best response WITH disclaimer
# - Logging on every attempt for tuning visibility
# ---------------------------------------------------------------------------

def scorer_node(state: AgentState) -> dict:

    messages = state["messages"]

    # Extract original user query
    user_query = next(
        (m.content for m in messages if isinstance(m, HumanMessage)), ""
    )

    # Collect all tool results from message history
    tool_data = [
        m.content for m in messages
        if isinstance(m, ToolMessage)
    ]

    # Get the first LLM final response (produced by agent_node)
    current_response = next(
        (m.content for m in reversed(messages) if isinstance(m, AIMessage)), ""
    )

    # --- Retry loop ---
    attempts = []

    for attempt_num in range(1, MAX_ATTEMPTS + 1):

        # Score current response
        score_result = score_response(user_query, tool_data, current_response)
        score = score_result.get("score", 0.0)

        # Log every attempt — used during testing to tune thresholds
        print(f"[SCORER] Attempt {attempt_num}: {score:.2f}")

        # Store this attempt
        attempts.append((score, current_response))

        # Early exit: ceiling hit — response is good enough, no more retries
        if score >= CEILING_THRESHOLD:
            print(
                f"[SCORER] Ceiling reached at attempt {attempt_num}, serving immediately")
            print(f"[SCORER] Outcome: served")
            return {"messages": [AIMessage(content=current_response)]}

        # Whether score is 0.55 OR 0.28 OR 0.15 — retry if attempts remain
        # Floor is NOT checked here — every bad response gets retry chances
        if attempt_num < MAX_ATTEMPTS:
            retry_prompt = f"""
Your previous response was not sufficiently grounded in the tool data provided.

Original question: {user_query}

Tool data available:
{tool_data}

Rules for your retry:
- Every claim must reference a specific value from the tool data above
- Do not state anything that cannot be traced to the tool data
- If the tool data does not support an answer, say 'Insufficient data available'
- Be concise and specific
- Do not reference or expose the seller_id
"""
            current_response = generate_simple(retry_prompt)

    # --- After loop: pick best scoring attempt across all attempts ---
    best_score, best_response = max(attempts, key=lambda x: x[0])

    print(f"[SCORER] Serving: attempt {attempts.index((best_score, best_response)) + 1} "
          f"with score {best_score:.2f}")

    # Clean serve — best attempt cleared the floor
    if best_score >= FLOOR_THRESHOLD:
        print(f"[SCORER] Outcome: served")
        return {"messages": [AIMessage(content=best_response)]}

    # Below floor — show best attempt with disclaimer
    # Do not hide the response — seller deserves to see what was found
    else:
        print(
            f"[SCORER] Outcome: refused — best score {best_score:.2f} below floor")

        disclaimer = (
            f"\n\n---\n"
            f"Note: This response could not be fully verified against "
            f"The answer above may be incomplete or insufficiently grounded. "
            f"Please try rephrasing your question"
        )

        return {"messages": [AIMessage(content=best_response + disclaimer)]}


# ---------------------------------------------------------------------------
# MONGODB CHECKPOINTER
# Saves full state after every node.
# Restores on next request using thread_id — persistent per-seller history.
# ---------------------------------------------------------------------------

checkpointer = MongoDBSaver(client, db_name="Retail-Return")


# ---------------------------------------------------------------------------
# GRAPH COMPILATION
# Nodes, edges, and entry point — unchanged from original design.
# ---------------------------------------------------------------------------

builder = StateGraph(AgentState)

builder.add_node("scope_check", scope_check_node)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)
builder.add_node("scorer", scorer_node)

builder.set_entry_point("scope_check")

builder.add_conditional_edges("scope_check", scope_check_router)
builder.add_conditional_edges("agent", agent_router)
builder.add_edge("tools", "agent")
builder.add_edge("scorer", END)

graph = builder.compile(
    checkpointer=checkpointer,
)



# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# Called by chat.py (the FastAPI route). Unchanged from original design.
# ---------------------------------------------------------------------------

def run_chat(user_message: str, seller_id: str) -> str:
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "seller_id": seller_id,
    }

    config = {
    "configurable": {
        "thread_id": seller_id
    },
    "recursion_limit": 10
}
    result = graph.invoke(initial_state, config=config)

    # Extract final text response from last AIMessage
    final_message = next(
        (m.content for m in reversed(
            result["messages"]) if isinstance(m, AIMessage)),
        "No response generated."
    )

    return final_message
