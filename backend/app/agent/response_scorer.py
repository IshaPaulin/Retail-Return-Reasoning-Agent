"""
response_scorer.py

Owns ALL grounding/hallucination checks for the project:
    - Chatbot: free-text grounding check via LLM-as-judge   -> get_grounded_response()
    - Dashboard: closed-category validation, no LLM judge   -> generate_product_insight()

chatbot_pipeline.py   imports: get_grounded_response
dashboard_pipeline.py imports: generate_product_insight
"""

import json
import logging
from typing import Any, Dict, List

from app.agent.gemini_client import generate_simple
from app.tools.get_return_reason_breakdown import get_return_reasons_breakdown

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared low-level helpers (used by both sections below)
# ---------------------------------------------------------------------------

MAX_TOOL_DATA_CHARS = 6000


def _serialize_tool_data(tool_data: Dict[str, Any]) -> str:
    try:
        serialized = json.dumps(tool_data, default=str, indent=2)
    except Exception:
        serialized = str(tool_data)
    if len(serialized) > MAX_TOOL_DATA_CHARS:
        serialized = serialized[:MAX_TOOL_DATA_CHARS] + "\n... (truncated)"
    return serialized


def _safe_parse_json(raw: str) -> Dict[str, Any] | None:
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


# ===========================================================================
# SECTION 1 — CHATBOT GROUNDING (used by chatbot_pipeline.py only)
# ===========================================================================

DEFAULT_THRESHOLD = 0.7


def score_response(user_query: str, tool_data: Dict[str, Any], llm_response: str) -> Dict[str, Any]:
    """LLM-as-judge: grades free-text chatbot answers against tool data."""
    tool_data_str = _serialize_tool_data(tool_data)
    prompt = f"""You are a grounding verifier for a retail returns analysis assistant.
...
User query: {user_query}
Actual tool data returned: {tool_data_str}
Assistant's response: {llm_response}
Respond ONLY with valid JSON: {{"score": float, "grounded": bool, "issues": [...]}}
"""
    try:
        raw = generate_simple(prompt)
    except Exception:
        logger.exception("score_response failed, failing open")
        return {"score": 1.0, "grounded": True, "issues": []}

    result = _safe_parse_json(raw)
    if result is None or "score" not in result:
        return {"score": 1.0, "grounded": True, "issues": []}

    score = float(result.get("score", 1.0))
    return {
        "score": score,
        "grounded": bool(result.get("grounded", score >= DEFAULT_THRESHOLD)),
        "issues": result.get("issues", []) or [],
    }


def _retry_with_grounding(user_query: str, tool_data: Dict[str, Any], issues: List[str]) -> str:
    tool_data_str = _serialize_tool_data(tool_data)
    retry_prompt = f"""Your previous response contained unsupported claims: {issues}
Actual tool data: {tool_data_str}
Rewrite strictly based on this data. Original query: {user_query}"""
    return generate_simple(retry_prompt)


def get_grounded_response(user_query: str, tool_data: Dict[str, Any], llm_response: str,
                           threshold: float = DEFAULT_THRESHOLD) -> str:
    """Main entry point for chatbot_pipeline.py."""
    result = score_response(user_query, tool_data, llm_response)
    if result["score"] >= threshold:
        return llm_response

    try:
        return _retry_with_grounding(user_query, tool_data, result["issues"])
    except Exception:
        return f"{llm_response}\n\n⚠️ Note: parts of this analysis could not be fully verified."


# ===========================================================================
# SECTION 2 — DASHBOARD INSIGHT VALIDATION (used by dashboard_pipeline.py only)
# ===========================================================================

def build_insight_prompt(product_name: str, breakdown: dict) -> str:
    valid_categories = list(breakdown.keys())
    return f"""Return data for "{product_name}": {breakdown}
Valid categories (choose ONLY from this list): {valid_categories}
Return ONLY JSON: {{"issue_category": "<exact match>", "insight": "<1-2 sentences>"}}
"""


def generate_product_insight(product_id: str, seller_id: str, product_name: str) -> dict:
    """Main entry point for dashboard_pipeline.py."""
    breakdown = get_return_reasons_breakdown(product_id, seller_id)
    if not breakdown:
        return {"text": "Not enough return data yet.", "source": "no_data"}

    valid_categories = list(breakdown.keys())
    prompt = build_insight_prompt(product_name, breakdown)
    parsed = _safe_parse_json(generate_simple(prompt))

    if parsed is None or parsed.get("issue_category") not in valid_categories:
        retry_raw = generate_simple(prompt + f"\nMUST be one of {valid_categories} exactly.")
        parsed = _safe_parse_json(retry_raw)

        if parsed is None or parsed.get("issue_category") not in valid_categories:
            top_reason = max(breakdown, key=breakdown.get)
            return {
                "text": f"Top return reason: {top_reason.replace('_', ' ')} ({breakdown[top_reason]} returns).",
                "source": "fallback_deterministic",
            }

    return {"text": parsed["insight"], "source": "llm", "category": parsed["issue_category"]}