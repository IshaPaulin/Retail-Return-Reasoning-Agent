from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.agent.pipeline import run_dashboard_analysis
from app.auth.jwt import get_current_seller
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


def _to_object_id(value: str):
    try:
        return ObjectId(value)
    except Exception:
        return value


def _product_id_from_record(product: dict) -> str | None:
    product_id = product.get("product_id")
    if product_id:
        return str(product_id)
    record_id = product.get("_id")
    if record_id is not None:
        return str(record_id)
    return None


def _product_name_from_record(product: dict, fallback_id: str) -> str:
    return product.get("product_name") or product.get("name") or fallback_id


def _find_product_for_seller(product_id: str, seller_id: str):
    seller_key = _to_object_id(seller_id)

    product = products_collection.find_one(
        {"seller_id": seller_key, "product_id": product_id},
        {"_id": 0, "product_id": 1, "product_name": 1, "name": 1},
    )
    if product:
        return product

    product = products_collection.find_one(
        {"seller_id": seller_key, "_id": _to_object_id(product_id)},
        {"_id": 0, "product_id": 1, "product_name": 1, "name": 1},
    )
    if product:
        return product

    return products_collection.find_one(
        {"seller_id": seller_key, "name": product_id},
        {"_id": 0, "product_id": 1, "product_name": 1, "name": 1},
    )


def _analyse_one_fast(product: dict, seller_id: str) -> dict | None:
    product_id = _product_id_from_record(product)
    if not product_id:
        return None
    try:
        analysis = run_dashboard_analysis(
            product_id,
            seller_id,
            fast_mode=True,       # skips orders, feedback, anomalies, category, Gemini
            include_gemini=False,
        )
        return mongo_safe({
            "product_id": product_id,
            "product_name": _product_name_from_record(product, product_id),
            "risk_score": analysis.get("risk_score", 0),
            "confidence": analysis.get("confidence", "low"),
            "return_signal": analysis.get("return_signal", "Low"),
            "primary_pattern": analysis.get("primary_pattern", "No strong pattern detected"),
            "summary": analysis.get("summary", "No summary available."),
            "root_cause": analysis.get("root_cause", ""),
            "return_rate": analysis.get("return_rate", 0),
            "trend": analysis.get("trend", "stable"),
        })
    except Exception:
        return mongo_safe({
            "product_id": product_id,
            "product_name": _product_name_from_record(product, product_id),
            "risk_score": 0,
            "confidence": "low",
            "return_signal": "Low",
            "primary_pattern": "Analysis unavailable",
            "summary": "Could not analyse this product.",
            "root_cause": "",
            "return_rate": 0,
            "trend": "stable",
        })


@router.get("")
def get_dashboard(current_seller_id: str = Depends(get_current_seller)):
    seller_key = _to_object_id(current_seller_id)
    products = list(
        products_collection.find(
            {"seller_id": seller_key},
            {"_id": 1, "product_id": 1, "product_name": 1, "name": 1},
        )
    )

    if not products:
        return []

    # Run all products in parallel — instead of sequential 15s * N products
    # max_workers=4 keeps Gemini API pressure low (fast_mode doesn't call Gemini anyway)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_analyse_one_fast, product, current_seller_id): product
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
    current_seller_id: str = Depends(get_current_seller),
):
    product = _find_product_for_seller(product_id, current_seller_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    normalized_product_id = _product_id_from_record(product) or product_id

    try:
        analysis = run_dashboard_analysis(
            normalized_product_id,
            current_seller_id,
            fast_mode=False,      # full analysis
            include_gemini=True,  # Gemini narrative
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    result = {
        "product_id": normalized_product_id,
        "product_name": _product_name_from_record(product, normalized_product_id),
    }
    result.update(analysis)
    return mongo_safe(result)