from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from bson import ObjectId
from langgraph.types import Command

from app.agent.gemini_client import generate_json, generate_text
from app.database.connection import products_collection
from app.tools.compare_seller_products import compare_seller_products
from app.tools.detect_anomalies import detect_anomalies
from app.tools.get_customer_feedback import get_customer_feedback
from app.tools.get_product_return_data import get_product_return_data
from app.tools.get_return_reasons_breakdown import get_return_reasons_breakdown
from app.tools.get_sku_return_breakdown import get_sku_return_breakdown
from app.tools._mongo_helpers import json_safe, to_object_id


MAX_TOOL_ROUNDS = 2

# ---------------------------------------------------------------------------
# Role definition — single source of truth for what this agent is and isn't.
# Used in guard_node boundary check AND in all Gemini prompts so the
# persona is consistent across the entire conversation.
# ---------------------------------------------------------------------------
AGENT_ROLE = """
You are a retail returns analytics assistant embedded in a seller dashboard.

Your job is to help sellers understand and reduce product returns.

You can help with:
- Return rates, return counts, return trends for any product
- Why customers are returning products (return reasons breakdown)
- Which SKUs or variants are being returned most
- Customer feedback and complaint patterns
- Anomaly detection — sudden spikes or drops in returns
- Comparing return performance across all seller products
- General advice on how to reduce returns for a given pattern

You cannot help with:
- Anything unrelated to retail, products, orders, or returns
- General knowledge questions (weather, news, sports, cooking, etc.)
- Writing code, essays, or creative content
- Financial advice, legal advice, or medical questions
- Questions about other sellers or platforms
"""

BOUNDARY_CHECK_PROMPT = """
You are a strict scope-checker for a retail returns analytics assistant.

The assistant's role:
{role}

User message: "{query}"

Decide if this message is in scope for the assistant.

Rules:
- In scope: anything about returns, products, orders, feedback, SKUs, delivery, anomalies, trends, or general retail analytics questions
- In scope: greetings, clarifications, follow-up questions about a previous answer
- Out of scope: anything clearly unrelated to retail or returns (weather, news, jokes, coding help, etc.)
- When in doubt: mark as in_scope — it is better to attempt a helpful response than to refuse

Respond with JSON only:
{{"in_scope": true | false, "reason": "one short sentence"}}
"""


def _is_in_scope(query: str) -> tuple[bool, str]:
    """Uses Gemini to decide if the query is in scope for this agent.
    Falls back to True on any error — never block a user due to a Gemini failure."""
    prompt = BOUNDARY_CHECK_PROMPT.format(role=AGENT_ROLE, query=query)
    result = generate_json(
        prompt,
        system_instruction="You are a scope classifier. Return only valid JSON.",
        default={"in_scope": True, "reason": "fallback"},
    )
    in_scope = result.get("in_scope", True)
    reason = result.get("reason", "")
    return bool(in_scope), reason


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ChatState(TypedDict, total=False):
    query: str
    seller_id: str
    conversation_id: str
    thread_id: str
    intent: str
    next_node: str
    product_id: str | None
    product_scope: str
    selected_tools: list[str]
    used_tools: list[str]
    tool_reasons: dict[str, str]
    tool_results: list[dict[str, Any]]
    tool_rounds: int
    clarify_question: str
    final_response: str
    confidence: str
    tools_used: list[str]
    messages: list[dict[str, str]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    requires_product_id: bool
    handler: Callable[[str, str | None, str], Any]


def _tool_product_return_data(seller_id: str, product_id: str | None, query: str) -> Any:
    if not product_id:
        return {"error": "product_id is required"}
    return get_product_return_data(product_id, seller_id)


def _tool_return_reasons(seller_id: str, product_id: str | None, query: str) -> Any:
    if not product_id:
        return {"error": "product_id is required"}
    return get_return_reasons_breakdown(product_id, seller_id)


def _tool_sku_breakdown(seller_id: str, product_id: str | None, query: str) -> Any:
    if not product_id:
        return {"error": "product_id is required"}
    return get_sku_return_breakdown(product_id, seller_id)


def _tool_feedback(seller_id: str, product_id: str | None, query: str) -> Any:
    if not product_id:
        return {"error": "product_id is required"}
    return get_customer_feedback(product_id, seller_id)


def _tool_anomalies(seller_id: str, product_id: str | None, query: str) -> Any:
    if not product_id:
        return {"error": "product_id is required"}
    return detect_anomalies(product_id, seller_id)


def _tool_compare_products(seller_id: str, product_id: str | None, query: str) -> Any:
    return compare_seller_products(seller_id)


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "get_product_return_data": ToolSpec(
        name="get_product_return_data",
        description="Fetch raw return records for one product so we can inspect timeline, volume, and return evidence.",
        requires_product_id=True,
        handler=_tool_product_return_data,
    ),
    "get_return_reasons_breakdown": ToolSpec(
        name="get_return_reasons_breakdown",
        description="Count return reasons for one product so we can identify the dominant failure mode.",
        requires_product_id=True,
        handler=_tool_return_reasons,
    ),
    "get_sku_return_breakdown": ToolSpec(
        name="get_sku_return_breakdown",
        description="See which SKUs or variants are returned most often for one product.",
        requires_product_id=True,
        handler=_tool_sku_breakdown,
    ),
    "get_customer_feedback": ToolSpec(
        name="get_customer_feedback",
        description="Pull customer feedback for one product so we can detect complaint patterns.",
        requires_product_id=True,
        handler=_tool_feedback,
    ),
    "detect_anomalies": ToolSpec(
        name="detect_anomalies",
        description="Find spikes in product returns over time.",
        requires_product_id=True,
        handler=_tool_anomalies,
    ),
    "compare_seller_products": ToolSpec(
        name="compare_seller_products",
        description="Compare return counts across all products for the seller when no single product is specified.",
        requires_product_id=False,
        handler=_tool_compare_products,
    ),
}


def _safe_json(value: Any) -> str:
    return json.dumps(value, default=str, indent=2)


def _resolve_product_id(query: str, seller_id: str) -> str | None:
    query = query.strip()
    if not query:
        return None

    object_id_pattern = re.fullmatch(r"[0-9a-fA-F]{24}", query)
    if object_id_pattern:
        product = products_collection.find_one(
            {"_id": ObjectId(query), "seller_id": to_object_id(seller_id)},
            {"_id": 1},
        )
        if product:
            return str(product["_id"])

    tokens = [token for token in re.findall(r"[a-zA-Z0-9]+", query.lower()) if len(token) > 2]
    if not tokens:
        return None

    regex = "|".join(re.escape(token) for token in tokens[:6])
    product = products_collection.find_one(
        {
            "seller_id": to_object_id(seller_id),
            "$or": [
                {"product_name": {"$regex": regex, "$options": "i"}},
                {"name": {"$regex": regex, "$options": "i"}},
            ],
        },
        {"_id": 1},
    )
    if product:
        return str(product["_id"])

    query_lower = query.lower()
    best_match_id = None
    best_score = 0

    for candidate in products_collection.find({"seller_id": to_object_id(seller_id)}, {"_id": 1, "product_name": 1, "name": 1}):
        product_text = " ".join(
            str(candidate.get(field, "")) for field in ("product_name", "name")
        ).lower()
        if not product_text:
            continue

        if query_lower in product_text or product_text in query_lower:
            return str(candidate["_id"])

        score = sum(1 for token in tokens if token in product_text)
        if score > best_score:
            best_score = score
            best_match_id = str(candidate["_id"])

    if best_score >= 2:
        return best_match_id

    return None


def _tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "requires_product_id": spec.requires_product_id,
        }
        for spec in TOOL_REGISTRY.values()
    ]


def _summarize_tool_results(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in tool_results:
        compact.append(
            {
                "tool": item.get("tool"),
                "description": item.get("description"),
                "reason": item.get("reason"),
                "output": item.get("output"),
            }
        )
    return compact


def _is_data_query(query_lower: str) -> bool:
    return any(
        token in query_lower
        for token in (
            "compare",
            "versus",
            " vs ",
            " vs.",
            "difference",
            "diff",
            "return",
            "returns",
            "rate",
            "revenue",
            "reasons",
            "feedback",
            "sku",
            "anomaly",
            "anomalies",
        )
    )


def _normalize_tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", (text or "").lower()))


def _query_matches_name(query_lower: str, name: str) -> bool:
    name_tokens = _normalize_tokens(name)
    if not name_tokens:
        return False
    return name_tokens.issubset(_normalize_tokens(query_lower))


def _rank_tools_for_query(query_lower: str, product_id: str | None) -> list[str]:
    query_tokens = _normalize_tokens(query_lower)
    scores: list[tuple[int, str]] = []

    for tool_name, spec in TOOL_REGISTRY.items():
        if spec.requires_product_id and not product_id:
            continue

        description_tokens = _normalize_tokens(spec.description.replace("_", " ") + " " + spec.name)
        score = len(description_tokens & query_tokens)

        if tool_name == "compare_seller_products" and any(k in query_lower for k in ("compare", "versus", "difference", "diff", " vs ", " vs.")):
            score += 4
        if tool_name == "get_product_return_data" and product_id:
            score += 2

        scores.append((score, tool_name))

    selected = [tool for score, tool in sorted(scores, key=lambda item: (item[0], item[1]), reverse=True) if score > 0]
    return selected[:3]


def _find_mentioned_products(query_lower: str, seller_id: str, limit: int = 5) -> list[dict[str, str]]:
    products = list(
        products_collection.find(
            {"seller_id": to_object_id(seller_id)},
            {"_id": 1, "product_name": 1, "name": 1},
        )
    )
    matches: list[dict[str, str]] = []
    for product in products:
        name = product.get("product_name") or product.get("name") or ""
        if _query_matches_name(query_lower, name):
            matches.append(
                {
                    "product_id": str(product["_id"]),
                    "product_name": name,
                    "match_count": len(_normalize_tokens(name)),
                }
            )
    return sorted(matches, key=lambda item: (item["match_count"], item["product_name"]), reverse=True)[:limit]


def _get_product_name(product_id: str, seller_id: str) -> str:
    product = products_collection.find_one(
        {"_id": to_object_id(product_id), "seller_id": to_object_id(seller_id)},
        {"product_name": 1, "name": 1},
    )
    if not product:
        return product_id
    return product.get("product_name") or product.get("name") or product_id


def _build_compare_response(query: str, tool_results: list[dict[str, Any]], seller_id: str) -> str:
    compare_tool = next((item for item in tool_results if item.get("tool") == "compare_seller_products"), None)
    if not compare_tool:
        return ""

    output = _parse_tool_output(compare_tool.get("output"))
    if not isinstance(output, list) or not output:
        return _fallback_tool_summary(tool_results)

    query_lower = query.lower()
    mentions = _find_mentioned_products(query_lower, seller_id)
    lines: list[str] = []

    if mentions:
        for mention in mentions:
            row = next(
                (
                    r
                    for r in output
                    if r.get("product_name", "").lower() == mention["product_name"].lower()
                    or r.get("product_id") == mention["product_id"]
                ),
                None,
            )
            if row:
                lines.append(f"{row.get('product_name')}: {row.get('return_count', 0)} returns")

    if lines:
        return "Here are the return counts for the products mentioned in your question:\n" + "\n".join(f"- {line}" for line in lines)

    top = sorted(output, key=lambda x: x.get("return_count", 0), reverse=True)[:3]
    if top:
        return "Here are the top returning products for your seller:\n" + "\n".join(
            f"- {row.get('product_name')}: {row.get('return_count', 0)} returns" for row in top
        )

    return "No seller return counts are available."


def _build_product_response(query: str, tool_results: list[dict[str, Any]], seller_id: str, product_id: str) -> str:
    product_name = _get_product_name(product_id, seller_id)
    pieces: list[str] = []

    reasons_item = next((item for item in tool_results if item.get("tool") == "get_return_reasons_breakdown"), None)
    sku_item = next((item for item in tool_results if item.get("tool") == "get_sku_return_breakdown"), None)
    feedback_item = next((item for item in tool_results if item.get("tool") == "get_customer_feedback"), None)
    anomalies_item = next((item for item in tool_results if item.get("tool") == "detect_anomalies"), None)
    raw_item = next((item for item in tool_results if item.get("tool") == "get_product_return_data"), None)

    if reasons_item:
        output = _parse_tool_output(reasons_item.get("output"))
        if isinstance(output, dict) and output:
            pieces.append(f"For {product_name}, the top return reasons are:")
            for reason, count in sorted(output.items(), key=lambda x: x[1], reverse=True)[:3]:
                pieces.append(f"- {reason}: {count}")

    if sku_item:
        output = _parse_tool_output(sku_item.get("output"))
        if isinstance(output, list) and output:
            pieces.append("Top returned SKUs or variants are:")
            for row in output[:3]:
                pieces.append(
                    f"- {row.get('variant') or row.get('sku_id', 'sku')}: {row.get('return_count', 0)} returns"
                )

    if feedback_item:
        output = _parse_tool_output(feedback_item.get("output"))
        if isinstance(output, list) and output:
            pieces.append(f"Found {len(output)} customer feedback items that relate to {product_name}.")

    if anomalies_item:
        output = _parse_tool_output(anomalies_item.get("output"))
        if output:
            pieces.append("Anomaly detection found potential issues in recent return activity for this product.")

    if not pieces and raw_item:
        output = _parse_tool_output(raw_item.get("output"))
        if isinstance(output, list):
            pieces.append(f"{product_name} has {len(output)} return records available for analysis.")

    if pieces:
        return " ".join(pieces)
    return _fallback_tool_summary(tool_results)


def _build_tool_response(query: str, tool_results: list[dict[str, Any]], seller_id: str, product_id: str | None) -> str:
    query_lower = query.lower()
    if any(x in query_lower for x in ("compare", "versus", " vs ", " vs.", "difference", "diff")):
        response = _build_compare_response(query, tool_results, seller_id)
        if response:
            return response
    if product_id:
        response = _build_product_response(query, tool_results, seller_id, product_id)
        if response:
            return response
    return _fallback_tool_summary(tool_results)


def _assistant_prompt(query: str, tool_results: list[dict[str, Any]]) -> str:
    return f"""
{AGENT_ROLE}

Answer the user's question directly and honestly.
Use the provided tool evidence if it exists.
Do not invent product counts or return statistics.
If the evidence is not enough, say what is missing and ask for the smallest useful follow-up.

User question:
{query}

Tool evidence:
{_safe_json(_summarize_tool_results(tool_results))}
""".strip()


def _route_prompt(state: ChatState) -> str:
    return f"""
{AGENT_ROLE}

You are routing a retail seller chat agent.

Choose the next node and the tools only from the tool catalog.
Prefer fallback_node when the user only needs a general answer and no live data.
Prefer tool_node when fresh seller data is needed.
Use synthesis_node after you have enough evidence from tools.
If a product-specific question needs a product but none is clear, ask a short clarification.

Return valid JSON only with keys:
- next_node: one of ["tool_node", "fallback_node", "synthesis_node", "final_node"]
- intent: a short label like "general_help", "product_analysis", "seller_comparison", "clarification"
- selected_tools: list of tool names
- reason: short routing reason
- clarify_question: string or empty string

State:
{_safe_json({
    "query": state.get("query", ""),
    "seller_id": state.get("seller_id", ""),
    "product_id": state.get("product_id"),
    "tool_rounds": state.get("tool_rounds", 0),
    "used_tools": state.get("used_tools", []),
    "tool_results": _summarize_tool_results(state.get("tool_results", [])),
})}

Tool catalog:
{_safe_json(_tool_catalog())}
""".strip()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def guard_node(state: ChatState) -> Command:
    query = (state.get("query") or "").strip()

    # Empty query
    if not query:
        return Command(
            goto="final_node",
            update={
                "intent": "clarification",
                "final_response": "Please send a question about your products, returns, or seller analytics.",
                "confidence": "low",
                "tools_used": [],
            },
        )

    # Greetings and very short messages pass through immediately —
    # no point burning a Gemini call on "hi" or "hello"
    if len(query) < 15 and any(w in query.lower() for w in ("hi", "hello", "hey", "thanks", "ok", "okay")):
        return Command(
            goto="final_node",
            update={
                "intent": "greeting",
                "final_response": (
                    "Hi! I'm your returns analytics assistant. "
                    "Ask me about your return rates, reasons, SKU breakdowns, "
                    "anomalies, or customer feedback."
                ),
                "confidence": "high",
                "tools_used": [],
            },
        )

    # Role-based boundary check via Gemini
    in_scope, reason = _is_in_scope(query)

    if not in_scope:
        return Command(
            goto="final_node",
            update={
                "intent": "out_of_scope",
                "final_response": (
                    "I'm only able to help with retail returns analytics — "
                    "things like return rates, return reasons, product feedback, "
                    "SKU breakdowns, anomalies, and seller comparisons. "
                    "Is there something along those lines I can help you with?"
                ),
                "confidence": "low",
                "tools_used": [],
            },
        )

    return Command(
        goto="route_node",
        update={
            "messages": state.get("messages", []) + [{"role": "user", "content": query}],
        },
    )


def route_node(state: ChatState) -> Command:
    query = state.get("query", "")
    seller_id = state.get("seller_id", "")
    tool_rounds = state.get("tool_rounds", 0)
    product_id = state.get("product_id") or _resolve_product_id(query, seller_id)
    tool_results = state.get("tool_results", [])

    if product_id:
        state_product_scope = "product"
    elif any(word in query.lower() for word in ("compare", "which", "best", "worst", "top", "highest", "lowest")):
        state_product_scope = "seller"
    else:
        state_product_scope = "seller"

    route_result = generate_json(
        _route_prompt(
            {
                **state,
                "product_id": product_id,
                "product_scope": state_product_scope,
            }
        ),
        system_instruction=(
            "You are a routing controller for a retail chat graph. "
            "Return JSON only. Be concise and grounded."
        ),
        default={
            "next_node": "fallback_node" if not tool_results else "synthesis_node",
            "intent": "general_help" if not tool_results else "analysis",
            "selected_tools": [],
            "reason": "Fallback routing.",
            "clarify_question": "",
        },
    )

    next_node = route_result.get("next_node", "fallback_node")
    selected_tools = [tool for tool in route_result.get("selected_tools", []) if tool in TOOL_REGISTRY]
    intent = route_result.get("intent", "analysis")
    clarify_question = route_result.get("clarify_question", "")

    query_lower = query.lower()
    is_compare_query = any(x in query_lower for x in ("compare", "versus", " vs ", " vs.", "difference", "diff"))
    is_data_query = bool(product_id) or is_compare_query or _is_data_query(query_lower)

    if next_node == "fallback_node" and not tool_results and is_data_query:
        next_node = "tool_node"

    if next_node == "final_node" and not clarify_question and is_data_query:
        next_node = "tool_node"

    if tool_rounds >= MAX_TOOL_ROUNDS and next_node == "tool_node":
        next_node = "synthesis_node"

    if next_node == "tool_node":
        if not selected_tools:
            selected_tools = _rank_tools_for_query(query_lower, product_id)
            if not selected_tools:
                selected_tools = ["compare_seller_products"] if not product_id else ["get_product_return_data"]

        selected_tools = [tool for tool in selected_tools if tool in TOOL_REGISTRY]
        if product_id is None:
            selected_tools = [tool for tool in selected_tools if not TOOL_REGISTRY[tool].requires_product_id]
        if not selected_tools:
            next_node = "fallback_node"

    if next_node == "synthesis_node" and not tool_results:
        next_node = "fallback_node"

    if next_node == "final_node" and clarify_question:
        return Command(
            goto="final_node",
            update={
                "intent": intent,
                "final_response": clarify_question,
                "confidence": "medium",
                "tools_used": [],
            },
        )

    return Command(
        goto=next_node,
        update={
            "intent": intent,
            "product_id": product_id,
            "selected_tools": selected_tools,
            "clarify_question": clarify_question,
        },
    )


def tool_node(state: ChatState) -> Command:
    query = state.get("query", "")
    seller_id = state.get("seller_id", "")
    product_id = state.get("product_id")
    selected_tools = state.get("selected_tools", [])
    used_tools = list(state.get("used_tools", []))
    tool_results = list(state.get("tool_results", []))

    for tool_name in selected_tools:
        if tool_name not in TOOL_REGISTRY:
            continue
        spec = TOOL_REGISTRY[tool_name]
        output = spec.handler(seller_id, product_id, query)
        tool_results.append({
            "tool": spec.name,
            "description": spec.description,
            "reason": spec.description,
            "output": json_safe(output),
        })
        if spec.name not in used_tools:
            used_tools.append(spec.name)

    return Command(
        goto="route_node",
        update={
            "tool_results": tool_results,
            "used_tools": used_tools,
            "selected_tools": [],
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        },
    )


def fallback_node(state: ChatState) -> dict[str, Any]:
    query = state.get("query", "")
    prompt = _assistant_prompt(query, state.get("tool_results", []))
    response = generate_text(
        prompt,
        system_instruction="You are a concise retail analytics assistant. Answer from general knowledge when no tools are needed.",
    )
    return {
        "final_response": response or "I can help, but I need either a specific product or a dashboard tool result to answer with precision.",
        "confidence": "medium",
    }


def _parse_tool_output(output: Any) -> Any:
    if isinstance(output, str):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    return output


def _fallback_tool_summary(tool_results: list[dict[str, Any]]) -> str:
    pieces: list[str] = []
    for item in tool_results:
        tool = item.get("tool")
        output = _parse_tool_output(item.get("output"))

        if tool == "compare_seller_products":
            if isinstance(output, list) and output:
                sorted_products = sorted(output, key=lambda x: x.get("return_count", 0), reverse=True)
                top = sorted_products[:3]
                pieces.append("Seller return counts by product:")
                for row in top:
                    pieces.append(f"- {row.get('product_name')}: {row.get('return_count', 0)} returns")
            else:
                pieces.append("No return counts were found for this seller.")

        elif tool == "get_product_return_data":
            if isinstance(output, list):
                pieces.append(f"Found {len(output)} return records for the product.")
                reasons = {}
                for rec in output:
                    category = rec.get("return_reason_category") or rec.get("return_reason") or "Unknown"
                    reasons[category] = reasons.get(category, 0) + 1
                top_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:3]
                if top_reasons:
                    pieces.append("Top return reasons:")
                    for reason, count in top_reasons:
                        pieces.append(f"- {reason}: {count}")
            else:
                pieces.append("No returns were found for this product.")

        elif tool == "get_return_reasons_breakdown":
            if isinstance(output, dict) and output:
                pieces.append("Return reasons breakdown:")
                for reason, count in sorted(output.items(), key=lambda x: x[1], reverse=True)[:5]:
                    pieces.append(f"- {reason}: {count}")
            else:
                pieces.append("No return reasons data available.")

        elif tool == "get_sku_return_breakdown":
            if isinstance(output, list) and output:
                pieces.append("Top SKU return breakdown:")
                for row in output[:5]:
                    pieces.append(f"- {row.get('variant') or row.get('sku_id', 'sku')}: {row.get('return_count', 0)} returns")
            else:
                pieces.append("No SKU return breakdown available.")

        elif tool == "detect_anomalies":
            if output:
                pieces.append("Anomaly detection returned evidence.")
            else:
                pieces.append("No anomalies were detected.")

        elif tool == "get_customer_feedback":
            if isinstance(output, list) and output:
                pieces.append(f"Found {len(output)} customer feedback items.")
            else:
                pieces.append("No customer feedback found.")

    return " ".join(pieces).strip()


def _is_weak_response(text: str) -> bool:
    if not text:
        return True
    weak_patterns = [
        "not enough evidence",
        "not enough information",
        "i can help, but",
        "i need",
        "cannot",
        "don't have",
        "do not have",
        "not enough",
    ]
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in weak_patterns)


def synthesis_node(state: ChatState) -> dict[str, Any]:
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    product_id = state.get("product_id")
    if tool_results:
        response = _build_tool_response(query, tool_results, state.get("seller_id", ""), product_id)
        if response:
            return {
                "final_response": response,
                "confidence": "high",
            }
    prompt = _assistant_prompt(query, tool_results)
    response = generate_text(
        prompt,
        system_instruction="You are a grounded retail analyst. Use only the provided tool evidence. If evidence is incomplete, ask for the smallest useful follow-up.",
    )
    if tool_results and (_is_weak_response(response) or not response):
        response = _fallback_tool_summary(tool_results)
    if not response:
        response = "I have some evidence, but it is not enough to give a confident answer yet."
    return {
        "final_response": response,
        "confidence": "high" if tool_results else "medium",
    }


def final_node(state: ChatState) -> dict[str, Any]:
    response = state.get("final_response") or "I do not have enough information to answer yet."
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": response})
    return {
        "response": response,
        "messages": messages,
        "tools_used": state.get("used_tools", []),
        "confidence": state.get("confidence", "medium"),
        "conversation_id": state.get("conversation_id") or state.get("thread_id") or state.get("seller_id", ""),
        "tool_results": state.get("tool_results", []),
    }


def _run_state_machine(initial_state: ChatState) -> dict[str, Any]:
    state = initial_state.copy()
    current = guard_node(state)

    while True:
        if isinstance(current, Command):
            state.update(current.update or {})
            if current.goto == "route_node":
                current = route_node(state)
                continue
            if current.goto == "tool_node":
                current = tool_node(state)
                continue
            if current.goto == "fallback_node":
                current = fallback_node(state)
                continue
            if current.goto == "synthesis_node":
                current = synthesis_node(state)
                continue
            if current.goto == "final_node":
                return final_node(state)
            return final_node(state)

        if isinstance(current, dict):
            state["final_response"] = current.get("final_response") or current.get("response")
            state["confidence"] = current.get("confidence", state.get("confidence", "medium"))
            return final_node(state)

        return final_node(state)


def run_chat(query: str, seller_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    thread_id = conversation_id or seller_id
    initial_state: ChatState = {
        "query": query,
        "seller_id": seller_id,
        "conversation_id": conversation_id or thread_id,
        "thread_id": thread_id,
        "messages": [{"role": "user", "content": query}],
        "selected_tools": [],
        "used_tools": [],
        "tool_reasons": {},
        "tool_results": [],
        "tool_rounds": 0,
    }

    result = _run_state_machine(initial_state)

    return {
        "response": result.get("response", ""),
        "intent": result.get("intent", ""),
        "confidence": result.get("confidence", "medium"),
        "tools_used": result.get("tools_used", []),
        "conversation_id": result.get("conversation_id", thread_id),
        "tool_results": result.get("tool_results", []),
    }