from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.agent.dashboard_pipeline import run_dashboard_analysis
from app.auth.jwt import validate_token
from app.database.connection import products_collection

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def mongo_safe(data):
    if isinstance(data, dict):
        return {k: mongo_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [mongo_safe(i) for i in data]
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, datetime):
        return data.isoformat()
    return data


def _product_id_from_record(product: dict) -> str | None:
    # Schema PK is _id (ObjectId) — no separate product_id field
    record_id = product.get("_id")
    if record_id is not None:
        return str(record_id)
    return None


def _product_name_from_record(product: dict, fallback_id: str) -> str:
    # Schema only has product_name — no "name" alias
    return product.get("product_name") or fallback_id


def _find_product_for_seller(product_id: str, seller_id: str):
    seller_key = ObjectId(seller_id)

    # Only valid lookup: by _id (the actual PK per schema)
    product = products_collection.find_one(
        {
            "seller_id": seller_key,
            "_id": ObjectId(product_id),
        },
        {"_id": 1, "product_name": 1},  # only fetch schema-valid fields
    )
    return product  # None if not found


def _analyse_one_full(product: dict, seller_id: str) -> dict | None:
    """
    Runs the full scoring pipeline (fast_mode=False) so risk_score and
    return_signal are consistent with the detail page, but skips Gemini
    (include_gemini=False) to avoid burning API quota across every product
    on every dashboard load. Gemini narrative is only fetched on the detail page.
    """
    product_id = _product_id_from_record(product)
    if not product_id:
        return None
    try:
        analysis = run_dashboard_analysis(
            product_id,
            seller_id,
            fast_mode=False,
            include_gemini=False,
        )
        return mongo_safe({
            "product_id": product_id,
            "product_name": _product_name_from_record(product, product_id),
            "risk_score": analysis.get("risk_score", 0),
            "return_signal": analysis.get("return_signal", "Low"),
            "primary_pattern": analysis.get("primary_pattern", "No strong pattern detected"),
            "summary": analysis.get("summary", "No summary available."),
            "root_cause": analysis.get("root_cause", ""),
            "return_rate": analysis.get("return_rate", 0),
            "trend": analysis.get("trend", "stable"),
            "trend_growth_rate": analysis.get("trend_growth_rate", 0),
            "worst_variant": analysis.get("worst_variant", {}),
            "category_comparison": analysis.get("category_comparison", {}),
            "score_components": analysis.get("score_components", {}),
            "supporting_points": analysis.get("supporting_points", []),
            "recommendations": analysis.get("recommendations", []),
            "evidence": analysis.get("evidence", {}),
        })
    except Exception as exc:
        return mongo_safe({
            "product_id": product_id,
            "product_name": _product_name_from_record(product, product_id),
            "risk_score": 0,
            "return_signal": "Low",
            "primary_pattern": "Analysis unavailable",
            "summary": f"Could not analyse this product: {exc}",
            "root_cause": "",
            "return_rate": 0,
            "trend": "stable",
            "trend_growth_rate": 0,
            "worst_variant": {},
            "category_comparison": {},
            "score_components": {},
            "supporting_points": [],
            "recommendations": [],
            "evidence": {},
        })


@router.get("")
def get_dashboard(current_seller_id: str = Depends(validate_token)):
    seller_key = ObjectId(current_seller_id)
    products = list(
        products_collection.find(
            {"seller_id": seller_key},
            {"_id": 1, "product_name": 1},  # only schema-valid fields
        )
    )

    if not products:
        return []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_analyse_one_full, product, current_seller_id): product
            for product in products
        }
        response = []
        for future in as_completed(futures):
            result = future.result()
            if result:
                response.append(result)

    return response


@router.get("/product/{product_id}")
def get_product_detail(
    product_id: str,
    current_seller_id: str = Depends(validate_token),
):
    product = _find_product_for_seller(product_id, current_seller_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # _id is the canonical ID per schema
    normalized_product_id = _product_id_from_record(product) or product_id

    try:
        analysis = run_dashboard_analysis(
            normalized_product_id,
            current_seller_id,
            fast_mode=False,
            include_gemini=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    result = {
        "product_id": normalized_product_id,
        "product_name": _product_name_from_record(product, normalized_product_id),
    }
    result.update(analysis)
    return mongo_safe(result)