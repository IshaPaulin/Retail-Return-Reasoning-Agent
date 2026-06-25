# app/agent/chatbot_pipeline.py

import inspect
from langgraph.graph import StateGraph, END
from langgraph.graph.message import MessagesState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.scope_check import check_scope
from app.agent.gemini_client import generate_with_tools, convert_messages
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

AGENT_SYSTEM_PROMPT = """You are a retail returns analytics assistant for a seller dashboard.

CRITICAL RULES — follow these without exception:
1. NEVER ask the user for a product_id or any database identifier.
2. If the user mentions a product by name, ALWAYS call compare_seller_products 
   first to get all products and their IDs, identify the matching product, 
   then use its product_id in all subsequent tool calls.
3. seller_id is always injected automatically — never ask for it.
4. Answer only questions about returns, products, orders, feedback, SKUs,
   delivery, and anomalies for this seller.

User question: """


class AgentState(MessagesState):
    seller_id: str
    scope_passed: bool = True


def scope_check_node(state: AgentState) -> dict:
    user_message = next(
        (m.content for m in state["messages"] if isinstance(m, HumanMessage)), ""
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


def agent_node(state: AgentState) -> dict:
    messages = list(state["messages"])

    tool_call_count = sum(
        1 for m in messages
        if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls
    )

    # On the first agent call, prepend system instructions directly into
    # the first HumanMessage content. This is because convert_messages maps
    # SystemMessage → "user" role, which Gemini doesn't treat as authoritative.
    # Prepending into the HumanMessage ensures Gemini reads the rules first.
    if tool_call_count == 0:
        first_human_idx = next(
            (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), None
        )
        if first_human_idx is not None:
            original_content = messages[first_human_idx].content
            messages[first_human_idx] = HumanMessage(
                content=f"{AGENT_SYSTEM_PROMPT}{original_content}"
            )

    if tool_call_count >= 3:
        messages.append(SystemMessage(
            content=(
                "You have gathered enough data. Stop calling tools now and "
                "synthesize a final answer based on the tool results already collected."
            )
        ))

    gemini_contents = convert_messages(messages)
    response = generate_with_tools(gemini_contents, ALL_TOOL_SCHEMAS)

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

    tool_call_count = sum(
        1 for m in state["messages"]
        if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls
    )

    if tool_call_count >= 4:
        return END
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


def tool_node(state: AgentState) -> dict:
    seller_id = state["seller_id"]
    last_message = state["messages"][-1]
    tool_results = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = dict(tool_call["args"])
        tool_args["seller_id"] = seller_id

        try:
            if tool_name not in TOOL_REGISTRY:
                raise KeyError(f"Unknown tool: {tool_name}")

            fn = TOOL_REGISTRY[tool_name]
            valid_params = inspect.signature(fn).parameters
            tool_args = {k: v for k, v in tool_args.items() if k in valid_params}

            result = fn(**tool_args)

        except KeyError as e:
            result = {"error": f"Unknown tool requested: {str(e)}"}
        except TypeError as e:
            result = {"error": f"Invalid arguments for tool {tool_name}: {str(e)}"}
        except Exception as e:
            result = {"error": f"Tool execution failed for {tool_name}: {str(e)}"}

        tool_results.append(
            ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    return {"messages": tool_results}


builder = StateGraph(AgentState)

builder.add_node("scope_check", scope_check_node)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)

builder.set_entry_point("scope_check")

builder.add_conditional_edges("scope_check", scope_check_router)
builder.add_conditional_edges("agent", agent_router)
builder.add_edge("tools", "agent")

graph = builder.compile()


def run_chat(user_message: str, seller_id: str) -> str:
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "seller_id": seller_id,
    }

    config = {
        "configurable": {"thread_id": seller_id},
        "recursion_limit": 25,
    }

    result = graph.invoke(initial_state, config=config)

    final_message = next(
        (m.content for m in reversed(result["messages"])
         if isinstance(m, AIMessage) and m.content),
        "No response generated."
    )

    return final_message