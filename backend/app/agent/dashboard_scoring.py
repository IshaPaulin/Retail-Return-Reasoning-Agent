from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any
from bson import ObjectId

from app.agent.gemini_client import generate_json
from app.database.connection import (
    categories_collection,
    orders_collection,
    products_collection,
    returns_collection,
    skus_collection,
)
from app.tools.detect_anomalies import detect_anomalies
from app.tools.get_customer_feedback import get_customer_feedback
from app.tools.get_return_reasons_breakdown import get_return_reasons_breakdown
from app.tools.get_sku_return_breakdown import get_sku_return_breakdown


# ---------------------------------------------------------------------------
# Tunable weights. These are business judgement calls, not derived constants.
# Each weight is the MAXIMUM number of points that signal can contribute to
# the 0-100 risk score. They are intentionally kept in one place so they can
# be adjusted without touching the scoring logic itself.
# ---------------------------------------------------------------------------
CONFIG = {
    "return_rate_weight": 35, # how bad is the return rate itself
    "reason_weight": 15, # how severe are the stated return reasons
    "feedback_weight": 15, # how severe is negative customer feedback
    "anomaly_weight": 15, # how severe/recent are detected spikes
    "category_weight": 10, # how much worse than category average
    "trend_weight": 10, # is the trend getting worse recently
}

# A return rate at or above this fraction is treated as "as bad as it gets"
# for scoring purposes. 50% is a deliberately high ceiling so the score can
# keep discriminating between a 10% and a 40% return rate instead of
# saturating almost immediately.
RETURN_RATE_CEILING = 0.5

REASON_SEVERITY = {
    "defective product": 1.0,
    "defective": 1.0,
    "damage": 0.95,
    "damaged": 0.95,
    "wrong item": 0.9,
    "not as described": 0.85,
    "size issue": 0.75,
    "too small": 0.8,
    "too big": 0.8,
    "changed mind": 0.25,
    "buyer remorse": 0.25,
    "late delivery": 0.6,
}

FEEDBACK_SEVERITY_KEYWORDS = {
    "defect": 1.0,
    "broken": 1.0,
    "unsafe": 1.0,
    "safety": 1.0,
    "damage": 0.95,
    "damaged": 0.95,
    "quality": 0.9,
    "different": 0.8,
    "size": 0.8,
    "small": 0.8,
    "big": 0.8,
    "delivery": 0.7,
    "late": 0.7,
    "shipping": 0.7,
    "smell": 0.6,
    "color": 0.5,
}


# ---------------------------------------------------------------------------
# Small parsing / lookup helpers
# ---------------------------------------------------------------------------

def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for date_format in (
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%d-%m-%Y",
            "%m/%d/%Y",
        ):
            try:
                return datetime.strptime(value[:26], date_format)
            except ValueError:
                continue
    return None

def _product_doc(product_id: str) -> dict[str, Any] | None:
    return products_collection.find_one({"_id": ObjectId(product_id)})

def _product_name(product: dict[str, Any] | None, product_id: str) -> str:
    if not product:
        return product_id
    return product.get("product_name") or product.get("name") or product_id


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _sku_docs_for_product(product_id: str, seller_id: str) -> list[dict[str, Any]]:
    return list(
        skus_collection.find(
            {"seller_id": ObjectId(seller_id), "product_id": ObjectId(product_id)},
            {"_id": 1, "sku_code": 1, "variant_attributes": 1, "price": 1},
        )
    )


def _orders_for_skus(sku_ids: list[Any]) -> list[dict[str, Any]]:
    if not sku_ids:
        return []
    return list(
        orders_collection.find(
            {"sku_id": {"$in": sku_ids}},
            {"_id": 0, "sku_id": 1, "order_date": 1, "delivery_date": 1, "quantity": 1, "price": 1, "fulfilment_status": 1},
        )
    )


def _returns_for_skus(sku_ids: list[Any]) -> list[dict[str, Any]]:
    if not sku_ids:
        return []
    return list(
        returns_collection.find(
            {"sku_id": {"$in": sku_ids}},
            {"_id": 0, "sku_id": 1, "return_date": 1, "return_reason": 1, "return_reason_category": 1, "refund_amount": 1},
        )
    )


def _sales_units(orders: list[dict[str, Any]]) -> int:
    total = 0
    for order in orders:
        quantity = order.get("quantity")
        if isinstance(quantity, (int, float)):
            total += int(quantity)
        else:
            total += 1
    return total


def _sales_by_sku(orders: list[dict[str, Any]]) -> dict[str, int]:
    sales_by_sku: dict[str, int] = defaultdict(int)
    for order in orders:
        sku_id = order.get("sku_id")
        if sku_id is None:
            continue
        quantity = order.get("quantity")
        if isinstance(quantity, (int, float)):
            sales_by_sku[str(sku_id)] += int(quantity)
        else:
            sales_by_sku[str(sku_id)] += 1
    return dict(sales_by_sku)


# ---------------------------------------------------------------------------
# Metric calculations
# ---------------------------------------------------------------------------

def _return_rate(returns_count: int, sales_units: int) -> float:
    if sales_units <= 0:
        return 0.0
    return returns_count / sales_units


def _confidence(sales_units: int) -> tuple[int, str]:
    """Returns (0-100 confidence score, label). Low sales = low confidence
    that the observed return rate reflects the product's true behaviour."""
    if sales_units < 20:
        return 25, "low"
    if sales_units < 100:
        return 60, "medium"
    return 90, "high"


def _recent_window_counts(returns: list[dict[str, Any]]) -> dict[str, int]:
    now = datetime.utcnow()
    windows = {"7d": 0, "30d": 0, "90d": 0}
    for record in returns:
        record_date = _parse_date(record.get("return_date"))
        if not record_date:
            continue
        days = (now - record_date).days
        if days <= 7:
            windows["7d"] += 1
        if days <= 30:
            windows["30d"] += 1
        if days <= 90:
            windows["90d"] += 1
    return windows


def _monthly_return_trend(returns: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, int] = defaultdict(int)
    for record in returns:
        record_date = _parse_date(record.get("return_date"))
        if not record_date:
            continue
        buckets[record_date.strftime("%Y-%m")] += 1

    if len(buckets) < 2:
        return {"trend": "stable", "growth_rate": 0.0, "series": dict(sorted(buckets.items()))}

    ordered = [count for _, count in sorted(buckets.items())]
    first, last = ordered[0], ordered[-1]
    growth_rate = 0.0 if first == 0 else (last - first) / first

    if growth_rate > 0.15:
        trend = "increasing"
    elif growth_rate < -0.15:
        trend = "decreasing"
    else:
        trend = "stable"

    return {"trend": trend, "growth_rate": growth_rate, "series": dict(sorted(buckets.items()))}


def _reason_severity_score(return_reasons: dict[str, int]) -> tuple[float, str]:
    """Returns (0-1 weighted severity, the single most severe reason label)."""
    if not return_reasons:
        return 0.0, ""

    weighted_sum = 0.0
    total_count = 0
    most_severe_reason = ""
    most_severe_score = -1.0

    for reason, count in return_reasons.items():
        key = reason.lower()
        severity = 0.5 # default for unrecognised reasons
        for token, token_score in REASON_SEVERITY.items():
            if token in key:
                severity = max(severity, token_score)
        weighted_sum += count * severity
        total_count += count
        if severity > most_severe_score:
            most_severe_score = severity
            most_severe_reason = reason

    avg_severity = (weighted_sum / total_count) if total_count else 0.0
    return avg_severity, most_severe_reason


def _feedback_severity(feedback: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Returns (0-1 average severity across feedback items, matched keywords)."""
    if not feedback:
        return 0.0, []

    severity_total = 0.0
    matched_keywords: list[str] = []

    for item in feedback:
        text = f"{item.get('comment_text') or item.get('comment') or ''}".lower()
        rating = item.get("rating")
        item_severity = 0.0
        if isinstance(rating, (int, float)) and rating <= 3:
            item_severity = 0.4 + ((3 - float(rating)) * 0.2)
        for token, token_score in FEEDBACK_SEVERITY_KEYWORDS.items():
            if token in text:
                item_severity = max(item_severity, token_score)
                matched_keywords.append(token)
        severity_total += min(item_severity, 1.0)

    return severity_total / len(feedback), matched_keywords


def _anomaly_severity(anomalies: dict[str, Any]) -> float:
    """Derives a 0-1 severity from detect_anomalies' spike-strings, using the
    actual multiple-of-average reported in each string rather than just
    treating "any anomaly" as one fixed severity."""
    if not anomalies.get("anomalies_detected"):
        return 0.0

    details = anomalies.get("details") or []
    if not details:
        return 0.3 # anomaly flagged true but no detail to size it -> mild default

    multiples: list[float] = []
    for line in details:
        # detect_anomalies formats spikes as "Spike in 2026-03: 9 returns"
        # We don't have the average baked into the string, so use count as
        # a relative proxy across buckets: more returns in a spike month
        # relative to other spike months = more severe.
        match = re.search(r"Recorded\s+(\d+)\s+returns", str(line))
        if match:
            multiples.append(float(match.group(1)))

    if not multiples:
        return 0.3

    # Normalise: scale the largest spike against a soft ceiling of 20 returns
    # in a single month being "severe". This is a judgement call, not a
    # statistically derived constant -- adjust if your order volumes differ.
    worst_spike = max(multiples)
    severity = min(worst_spike / 20.0, 1.0)
    return max(severity, 0.3) # any confirmed anomaly is at least mildly severe


def _category_ids(product: dict[str, Any]) -> list[Any]:
    category = product.get("category") or []
    if isinstance(category, list):
        return [c for c in category if c is not None]
    return [category] if category else []


def _category_benchmark(product: dict[str, Any]) -> dict[str, Any]:
    """Live, uncached lookup of how this product's category performs on
    average. No caching per explicit requirement -- this does a real query
    every call. Keep category sizes in mind; this scans every product in
    the category and fetches its SKUs/orders/returns."""
    category_ids = _category_ids(product)
    if not category_ids:
        return {"category_name": "Unknown", "average_return_rate": 0.0}

    category_doc = categories_collection.find_one(
        {"_id": {"$in": category_ids}}, {"_id": 1, "category_name": 1}
    )
    category_name = category_doc.get("category_name") if category_doc else "Unknown"

    category_products = list(
        products_collection.find({"category": {"$in": category_ids}}, {"_id": 1})
    )

    return_rates: list[float] = []
    for cat_product in category_products:
        sku_docs = list(skus_collection.find({"product_id": cat_product["_id"]}, {"_id": 1}))
        sku_ids = [sku["_id"] for sku in sku_docs]
        if not sku_ids:
            continue
        cat_orders = _orders_for_skus(sku_ids)
        cat_returns = _returns_for_skus(sku_ids)
        cat_sales = _sales_units(cat_orders)
        if cat_sales > 0:
            return_rates.append(_return_rate(len(cat_returns), cat_sales))

    average_return_rate = mean(return_rates) if return_rates else 0.0
    return {"category_name": category_name, "average_return_rate": average_return_rate}


def _worst_variant(sku_breakdown: list[dict[str, Any]], sales_by_sku: dict[str, int]) -> dict[str, Any]:
    worst = {"sku_id": "", "variant": "", "return_rate": 0.0, "return_count": 0}
    for item in sku_breakdown:
        sku_id = str(item.get("sku_id", ""))
        return_count = int(item.get("return_count", 0))
        sales = sales_by_sku.get(sku_id, 0)
        rate = _return_rate(return_count, sales)
        if rate > worst["return_rate"]:
            worst = {
                "sku_id": sku_id,
                "variant": item.get("variant", ""),
                "return_rate": rate,
                "return_count": return_count,
            }
    return worst


# ---------------------------------------------------------------------------
# Score assembly
# ---------------------------------------------------------------------------

def _score_components(
    return_rate: float,
    reason_severity: float,
    feedback_severity: float,
    anomaly_severity: float,
    relative_risk: float,
    trend: str,
    growth_rate: float,
) -> dict[str, float]:
    """Each component is reported in actual points contributed (already
    weighted), so the breakdown is directly explainable on the dashboard."""
    return_rate_component = min(return_rate / RETURN_RATE_CEILING, 1.0) * CONFIG["return_rate_weight"]
    reason_component = reason_severity * CONFIG["reason_weight"]
    feedback_component = feedback_severity * CONFIG["feedback_weight"]
    anomaly_component = anomaly_severity * CONFIG["anomaly_weight"]

    # relative_risk is product_rate / category_avg_rate. 1.0 = exactly average.
    # Only risk ABOVE category average should add points.
    category_component = min(max(relative_risk - 1.0, 0.0), 1.0) * CONFIG["category_weight"]

    if trend == "increasing":
        trend_component = min(abs(growth_rate), 1.0) * CONFIG["trend_weight"]
    elif trend == "decreasing":
        trend_component = -min(abs(growth_rate), 1.0) * (CONFIG["trend_weight"] * 0.6)
    else:
        trend_component = 0.0

    return {
        "return_rate": round(return_rate_component, 2),
        "reason_severity": round(reason_component, 2),
        "feedback_severity": round(feedback_component, 2),
        "anomaly": round(anomaly_component, 2),
        "category_relative": round(category_component, 2),
        "trend": round(trend_component, 2),
    }


def _total_score(components: dict[str, float], confidence_label: str) -> int:
    raw_total = sum(components.values())

    # Low-confidence (low sample size) results get dampened so a single
    # unlucky return on 2 sales doesn't read as a 100-point emergency.
    if confidence_label == "low":
        raw_total *= 0.7
    elif confidence_label == "medium":
        raw_total *= 0.9

    return max(0, min(round(raw_total), 100))


def _root_cause(return_reasons: dict[str, int], top_reason: str, feedback_keywords: list[str], sku_breakdown: list[dict[str, Any]]) -> str:
    if top_reason:
        low = top_reason.lower()
        if any(w in low for w in ("size", "small", "big", "fit")):
            return "Sizing or fit issues"
        if any(w in low for w in ("damage", "broken", "defect")):
            return "Quality or damage issues"
        if any(w in low for w in ("wrong item", "incorrect", "different")):
            return "Wrong-item or fulfillment issues"
        if any(w in low for w in ("late", "delivery", "shipping")):
            return "Delivery or shipping delays"
        return top_reason

    if feedback_keywords:
        if any(k in ("size", "small", "big") for k in feedback_keywords):
            return "Sizing or fit issues"
        if any(k in ("defect", "broken", "damage", "damaged") for k in feedback_keywords):
            return "Quality or damage issues"
        if any(k in ("delivery", "late", "shipping") for k in feedback_keywords):
            return "Delivery or shipping delays"

    if sku_breakdown:
        return "Variant-specific issue"

    return "No strong pattern detected"


# ---------------------------------------------------------------------------
# Gemini narrative layer
# ---------------------------------------------------------------------------

def _safe_json_text(value: Any) -> str:
    import json

    return json.dumps(value, default=str, indent=2)


def _gemini_dashboard_insight(
    product_id: str,
    product_name: str,
    risk_score: int,
    risk_label: str,
    confidence_label: str,
    return_rate: float,
    trend: str,
    score_components: dict[str, float],
    return_reasons: dict[str, int],
    feedback: list[dict[str, Any]],
    sku_breakdown: list[dict[str, Any]],
    worst_variant: dict[str, Any],
    category_comparison: dict[str, Any],
    fallback_root_cause: str,
) -> dict[str, Any]:
    prompt = f"""
You are a retail return analyst writing for a seller dashboard.

Return valid JSON only with these keys:
- card_insight: one short sentence for the dashboard summary card
- root_cause: the most likely reason returns are happening, in plain language
- summary: 2 to 3 sentences explaining the issue in plain language
- supporting_points: a list of up to 3 concise evidence points, grounded in the data given
- recommendations: a list of up to 3 specific, concrete seller actions
- confidence: one of "low", "medium", "high"

Do not use markdown. Do not add extra keys. Do not invent numbers that are not given below.

Product:
{_safe_json_text({
    "product_id": product_id,
    "product_name": product_name,
    "risk_score": risk_score,
    "risk_label": risk_label,
    "confidence": confidence_label,
})}

Metrics:
{_safe_json_text({
    "return_rate_pct": round(return_rate * 100, 2),
    "trend": trend,
    "score_components": score_components,
    "category_comparison": category_comparison,
    "worst_variant": worst_variant,
    "fallback_root_cause": fallback_root_cause,
})}

Evidence:
{_safe_json_text({
    "return_reasons": return_reasons,
    "feedback_samples": feedback[:5],
    "sku_breakdown": sku_breakdown,
})}
"""
    result = generate_json(
        prompt,
        system_instruction="Return only valid JSON. No markdown. No explanation outside JSON.",
    )

    return {
        "card_insight": result.get("card_insight", ""),
        "root_cause": result.get("root_cause", ""),
        "summary": result.get("summary", ""),
        "supporting_points": result.get("supporting_points", []),
        "recommendations": result.get("recommendations", []),
        "confidence": result.get("confidence", confidence_label),
    }


def _fallback_dashboard_insight(
    product_name: str,
    risk_label: str,
    fallback_root_cause: str,
    returns_count: int,
    sales_units: int,
    trend: str,
) -> dict[str, Any]:
    return {
        "card_insight": f"{risk_label} risk: {fallback_root_cause}",
        "root_cause": fallback_root_cause,
        "summary": (
            f"{product_name} has {returns_count} returns across {sales_units} sold units. "
            f"The current pattern looks {trend} and points to {fallback_root_cause.lower()}."
        ),
        "supporting_points": [
            f"{returns_count} returns across {sales_units} sold units.",
            f"Recent return trend: {trend}.",
            f"Primary pattern: {fallback_root_cause}.",
        ],
        "recommendations": [
            "Inspect the highest-risk variant and its product listing.",
            "Review the top return reason and address the underlying product or listing issue.",
            "Check recent feedback for matching complaint patterns.",
        ],
        "confidence": "medium" if sales_units < 100 else "high",
    }


def _build_fast_dashboard_card(
    product_name: str,
    return_count: int,
    top_reason: str,
    trend: str,
) -> dict[str, Any]:
    if return_count >= 10:
        risk_label = "High"
    elif return_count >= 3:
        risk_label = "Medium"
    else:
        risk_label = "Low"

    root_cause = top_reason or "No strong pattern detected"
    return {
        "risk_score": min(return_count * 10, 100),
        "return_signal": risk_label,
        "confidence": "low" if return_count < 20 else "medium",
        "return_rate": 0,
        "trend": trend,
        "root_cause": root_cause,
        "primary_pattern": root_cause,
        "summary": (
            f"{product_name} has {return_count} returns so far. "
            f"The visible pattern looks {trend} and points to {root_cause.lower()}."
        ),
        "supporting_points": [
            f"{return_count} returns observed.",
            f"Trend: {trend}.",
            f"Primary pattern: {root_cause}.",
        ],
        "recommendations": [
            "Review the top return reason and product details.",
            "Inspect the product detail page for a deeper breakdown.",
            "Look for variant-specific issues in the dashboard detail view.",
        ],
        "category_comparison": {"category_name": "Unknown", "average_return_rate": 0.0, "relative_risk": 0.0},
        "worst_variant": {"sku_id": "", "variant": "", "return_rate": 0.0, "return_count": 0},
        "score_components": {},
        "evidence": {"return_count": return_count},
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def analyze_product_dashboard(
    product_id: str,
    seller_id: str,
    product: dict[str, Any] | None = None,
    include_gemini: bool = False,
    fast_mode: bool = False,
) -> dict[str, Any]:
    product = product or _product_doc(product_id) or {}
    product_name = _product_name(product, product_id)

    sku_docs = _sku_docs_for_product(product_id, seller_id)
    sku_ids = [sku["_id"] for sku in sku_docs]
    returns = _returns_for_skus(sku_ids)

    if fast_mode:
        return_reasons = get_return_reasons_breakdown(product_id, seller_id)
        top_reason = max(return_reasons.items(), key=lambda item: item[1])[0] if return_reasons else ""
        trend_info = _monthly_return_trend(returns)
        card = _build_fast_dashboard_card(
            product_name=product_name,
            return_count=len(returns),
            top_reason=top_reason,
            trend=trend_info["trend"],
        )
        return {
            "product_id": product_id,
            "product_name": product_name,
            **card,
        }

    orders = _orders_for_skus(sku_ids)

    return_reasons = get_return_reasons_breakdown(product_id, seller_id)
    feedback = get_customer_feedback(product_id, seller_id)
    sku_breakdown = get_sku_return_breakdown(product_id, seller_id)
    anomalies = detect_anomalies(product_id, seller_id)

    sales_units = _sales_units(orders)
    sales_by_sku = _sales_by_sku(orders)
    returns_count = len(returns)
    return_rate = _return_rate(returns_count, sales_units)

    recent_windows = _recent_window_counts(returns)
    trend_info = _monthly_return_trend(returns)

    reason_severity, top_reason = _reason_severity_score(return_reasons)
    feedback_severity, feedback_keywords = _feedback_severity(feedback)
    anomaly_sev = _anomaly_severity(anomalies)
    confidence_score, confidence_label = _confidence(sales_units)
    category_benchmark = _category_benchmark(product)
    worst_variant = _worst_variant(sku_breakdown, sales_by_sku)

    relative_risk = 0.0
    if category_benchmark.get("average_return_rate"):
        relative_risk = return_rate / category_benchmark["average_return_rate"]

    components = _score_components(
        return_rate=return_rate,
        reason_severity=reason_severity,
        feedback_severity=feedback_severity,
        anomaly_severity=anomaly_sev,
        relative_risk=relative_risk,
        trend=trend_info["trend"],
        growth_rate=trend_info["growth_rate"],
    )
    risk_score = _total_score(components, confidence_label)

    if risk_score >= 66:
        risk_label = "High"
    elif risk_score >= 33:
        risk_label = "Medium"
    else:
        risk_label = "Low"

    fallback_root_cause = _root_cause(return_reasons, top_reason, feedback_keywords, sku_breakdown)

    category_comparison = {
        "category_name": category_benchmark.get("category_name", "Unknown"),
        "average_return_rate": round(category_benchmark.get("average_return_rate", 0.0), 4),
        "relative_risk": round(relative_risk, 4),
    }

    gemini_insight = _fallback_dashboard_insight(
        product_name=product_name,
        risk_label=risk_label,
        fallback_root_cause=fallback_root_cause,
        returns_count=returns_count,
        sales_units=sales_units,
        trend=trend_info["trend"],
    )

    if include_gemini:
        try:
            gemini_result = _gemini_dashboard_insight(
                product_id=product_id,
                product_name=product_name,
                risk_score=risk_score,
                risk_label=risk_label,
                confidence_label=confidence_label,
                return_rate=return_rate,
                trend=trend_info["trend"],
                score_components=components,
                return_reasons=return_reasons,
                feedback=feedback,
                sku_breakdown=sku_breakdown,
                worst_variant=worst_variant,
                category_comparison=category_comparison,
                fallback_root_cause=fallback_root_cause,
            )
            gemini_insight.update({k: v for k, v in gemini_result.items() if v})
        except Exception:
            pass

    return {
        "product_id": product_id,
        "product_name": product_name,
        "risk_score": risk_score,
        "return_signal": risk_label,
        "confidence_score": confidence_score,
        "confidence": gemini_insight["confidence"] or confidence_label,
        "return_rate": round(return_rate, 4),
        "trend": trend_info["trend"],
        "trend_growth_rate": round(trend_info["growth_rate"], 4),
        "score_components": components,
        "root_cause": gemini_insight["root_cause"] or fallback_root_cause,
        "summary": gemini_insight["card_insight"] or gemini_insight["summary"] or "No return records found for this product.",
        "primary_pattern": gemini_insight["root_cause"] or fallback_root_cause,
        "worst_variant": worst_variant,
        "category_comparison": category_comparison,
        "supporting_points": gemini_insight["supporting_points"] or [
            f"{returns_count} returns across {sales_units} sold units.",
            f"Top return reason: {top_reason or 'No strong pattern detected'}.",
            f"Recent return trend: {trend_info['trend']}.",
        ],
        "recommendations": gemini_insight["recommendations"] or [
            "Inspect the highest-risk variant and its product listing.",
            "Review the top return reason and address the underlying product or listing issue.",
            "Check recent feedback for matching complaint patterns.",
        ],
        "evidence": {
            "sales_units": sales_units,
            "return_count": returns_count,
            "recent_windows": recent_windows,
            "return_reasons": return_reasons,
            "feedback_count": len(feedback),
            "feedback_signals": feedback_keywords,
            "sku_breakdown": sku_breakdown,
            "anomalies": anomalies,
            "category_benchmark": category_benchmark,
        },
    }


def run_dashboard_analysis(
    product_id: str,
    seller_id: str,
    product: dict[str, Any] | None = None,
    include_gemini: bool = False,
    fast_mode: bool = False,
) -> dict[str, Any]:
    return analyze_product_dashboard(
        product_id,
        seller_id,
        product,
        include_gemini=include_gemini,
        fast_mode=fast_mode,
    )


'''def run_chat(query: str, seller_id: str) -> dict[str, Any]:
    lowered_query = query.lower()
    allowed_terms = ["return", "product", "order", "feedback", "delivery", "seller", "sku"]

    if not any(term in lowered_query for term in allowed_terms):
        return {
            "response": "I can only assist with return, product, order, and feedback related questions.",
            "tools_used": [],
        }

    return {
        "response": "Chat mode is connected, but Gemini tool calling will be added later.",
        "tools_used": ["scope_guard"],
    }'''