from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from app.agent.gemini_client import generate_simple
from app.agent.chatbot_pipeline import run_chat as run_chat_pipeline

from app.tools.detect_anomalies import detect_anomalies
from app.tools.get_customer_feedback import get_customer_feedback
from app.tools.get_order_delivery_data import get_order_delivery_data
from app.tools.get_product_return_data import get_product_return_data
from app.tools.get_return_reasons_breakdown import get_return_reasons_breakdown
from app.tools.get_return_trend import get_return_trend
from app.tools.get_sku_return_breakdown import get_sku_return_breakdown


def run_dashboard_analysis(
    product_id: str,
    seller_id: str,
    product: dict[str, Any] | None = None,
    include_gemini: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "product_id":       product_id,
        "product_name":     "Unknown Product",
        "return_rate":      0.0,
        "orders_count":     0,
        "return_count":     0,
        "avg_rating":       None,
        "anomaly":          False,
        "anomaly_message":  None,
        "risk_signal":      "Unknown",
        "error":            None,
    }

    # Step 1 — card metrics from pre-fetched compare_seller_products row
    if product:
        result["product_name"] = product.get("product_name", "Unknown Product")
        result["return_rate"]  = product.get("return_rate", 0.0)
        result["orders_count"] = product.get("orders_count", 0)
        result["return_count"] = product.get("return_count", 0)
        result["avg_rating"]   = product.get("avg_rating", None)

    # Step 2 — anomaly detection
    try:
        anomaly_result = detect_anomalies(product_id=product_id, seller_id=seller_id)
        detected = anomaly_result.get("anomalies_detected", False)
        details  = anomaly_result.get("details", [])
        result["anomaly"]         = detected
        result["anomaly_message"] = details[0] if detected and details else None
    except Exception as exc:
        result["error"] = f"Anomaly detection failed: {exc}"

    # Step 3 — Gemini risk signal from raw return history
    if include_gemini:
        try:
            result["risk_signal"] = _classify_risk(product_id, seller_id)
        except Exception as exc:
            result["risk_signal"] = "Unknown"
            result["error"] = (result["error"] or "") + f" | Gemini failed: {exc}"

    return result


def _classify_risk(product_id: str, seller_id: str) -> str:
    try:
        return_records = get_product_return_data(product_id, seller_id)
    except Exception:
        return "Unknown"

    if not return_records:
        return "Low"

    prompt = f"""
You are a retail analytics assistant. Below is the raw return history for a
single product. Classify the return risk as exactly one of: High, Medium, Low.

Guidelines:
- High   : frequent returns, strong pattern in reasons, or escalating volume
- Medium : moderate return volume or a single dominant reason emerging
- Low    : few returns, no clear pattern

Return History ({len(return_records)} records):
{json.dumps(return_records[:50], default=str, indent=2)}

Respond with a single JSON object and nothing else:
{{"risk_signal": "High" | "Medium" | "Low"}}
"""
    raw    = generate_simple(prompt)
    parsed = _parse_json(raw)
    signal = parsed.get("risk_signal", "Unknown")
    return signal if signal in ("High", "Medium", "Low") else "Unknown"


# ---------------------------------------------------------------------------
# PRODUCT DETAIL
# ---------------------------------------------------------------------------

def run_product_detail(
    product_id: str,
    seller_id: str,
) -> dict[str, Any]:
    
    detail: dict[str, Any] = {
        "product_id": product_id,
        "overview": {
            "available": False,
            "data": {
                "total_orders":      0,
                "total_returns":     0,
                "return_rate":       0.0,
                "avg_rating":        None,
                "avg_delivery_days": None,
            },
            "error": None,
        },
        "return_trend": {
            "available": False,
            "data": {"has_data": False, "trend": []},
            "error": None,
        },
        "return_reasons": {
            "available": False,
            "data": {},
            "error": None,
        },
        "customer_feedback": {
            "available": False,
            "data": [],
            "error": None,
        },
        "delivery": {
            "available": False,
            "data": {
                "total_orders":       0,
                "delivered_pct":      0.0,
                "cancelled_pct":      0.0,
                "returned_pct":       0.0,
                "pending_pct":        0.0,
                "shipped_pct":        0.0,
                "avg_delivery_days":  None,
                "delivery_durations": [],
            },
            "records": [],
            "error": None,
        },
        "anomalies": {
            "available": False,
            "data": {"anomalies_detected": False, "details": []},
            "error": None,
        },
        "sku_breakdown": {
            "available": False,
            "data": [],
            "error": None,
        },
    }

    # Fetch shared data once — reused across multiple sections
    return_records   = []
    feedback_docs    = []
    delivery_records = []

    # Section 1 — Overview KPIs
    try:
        return_records   = get_product_return_data(product_id, seller_id)
        feedback_docs    = get_customer_feedback(product_id, seller_id)
        delivery_records = get_order_delivery_data(product_id, seller_id)

        total_returns = len(return_records)
        total_orders  = len(delivery_records)
        return_rate   = round((total_returns / total_orders) * 100, 2) if total_orders else 0.0

        ratings = [f["rating"] for f in feedback_docs if isinstance(f.get("rating"), (int, float))]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

        durations = [r["delivery_duration_days"] for r in delivery_records if r.get("delivery_duration_days") is not None]
        avg_delivery_days = round(sum(durations) / len(durations), 1) if durations else None

        detail["overview"]["available"] = True
        detail["overview"]["data"] = {
            "total_orders":      total_orders,
            "total_returns":     total_returns,
            "return_rate":       return_rate,
            "avg_rating":        avg_rating,
            "avg_delivery_days": avg_delivery_days,
        }
    except Exception as exc:
        detail["overview"]["error"] = str(exc)

    # Section 2 — Return Trend
    try:
        trend_result = get_return_trend(seller_id, product_id)
        if trend_result.get("has_data"):
            detail["return_trend"]["available"] = True
            detail["return_trend"]["data"]      = trend_result
    except Exception as exc:
        detail["return_trend"]["error"] = str(exc)

    # Section 3 — Return Reasons
    try:
        reasons = get_return_reasons_breakdown(product_id, seller_id)
        if reasons:
            detail["return_reasons"]["available"] = True
            detail["return_reasons"]["data"]      = reasons
    except Exception as exc:
        detail["return_reasons"]["error"] = str(exc)

    # Section 4 — Customer Feedback
    try:
        if not feedback_docs:
            feedback_docs = get_customer_feedback(product_id, seller_id)
        if feedback_docs:
            detail["customer_feedback"]["available"] = True
            detail["customer_feedback"]["data"]      = _serialize(feedback_docs)
    except Exception as exc:
        detail["customer_feedback"]["error"] = str(exc)

    # Section 5 — Delivery Performance
    try:
        if not delivery_records:
            delivery_records = get_order_delivery_data(product_id, seller_id)
        if delivery_records:
            detail["delivery"]["available"] = True
            detail["delivery"]["data"]      = _summarise_delivery(delivery_records)
            detail["delivery"]["records"]   = _serialize(delivery_records)
    except Exception as exc:
        detail["delivery"]["error"] = str(exc)

    # Section 6 — Anomaly Insights
    try:
        anomaly_result = detect_anomalies(product_id, seller_id)
        detail["anomalies"]["available"] = anomaly_result.get("anomalies_detected", False)
        detail["anomalies"]["data"]      = anomaly_result
    except Exception as exc:
        detail["anomalies"]["error"] = str(exc)

    # Section 7 — SKU Breakdown (conditional)
    try:
        sku_data = get_sku_return_breakdown(product_id, seller_id)
        if sku_data:
            detail["sku_breakdown"]["available"] = True
            detail["sku_breakdown"]["data"]      = _serialize(sku_data)
    except Exception as exc:
        detail["sku_breakdown"]["error"] = str(exc)

    return detail


# ---------------------------------------------------------------------------
# CHAT
# ---------------------------------------------------------------------------

def run_chat(query: str, seller_id: str) -> dict[str, Any]:
    return run_chat_pipeline(query, seller_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarise_delivery(records: list[dict]) -> dict:
    total = len(records)
    if not total:
        return {}

    status_counts = Counter(r.get("fulfilment_status", "unknown") for r in records)
    durations = [r["delivery_duration_days"] for r in records if r.get("delivery_duration_days") is not None]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    def pct(n: int) -> float:
        return round((n / total) * 100, 1)

    return {
        "total_orders":       total,
        "delivered_pct":      pct(status_counts.get("delivered", 0)),
        "cancelled_pct":      pct(status_counts.get("cancelled", 0)),
        "returned_pct":       pct(status_counts.get("returned", 0)),
        "pending_pct":        pct(status_counts.get("pending", 0)),
        "shipped_pct":        pct(status_counts.get("shipped", 0)),
        "avg_delivery_days":  avg_duration,
        "delivery_durations": durations,
    }


def _parse_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


def _serialize(data: Any) -> Any:
    from bson import ObjectId
    from datetime import datetime

    if isinstance(data, list):
        return [_serialize(item) for item in data]
    if isinstance(data, dict):
        return {k: _serialize(v) for k, v in data.items()}
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, datetime):
        return data.isoformat()
    return data