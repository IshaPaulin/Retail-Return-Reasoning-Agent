from fastapi import APIRouter, Depends, HTTPException

from app.agent.pipeline import run_dashboard_analysis
from app.auth.jwt import get_current_seller
from app.database.connection import products_collection

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(current_seller_id: str = Depends(get_current_seller)):
    products = list(
        products_collection.find(
            {"seller_id": current_seller_id},
            {"_id": 0, "product_id": 1, "product_name": 1},
        )
    )

    response = []
    for product in products:
        product_id = product.get("product_id")
        if not product_id:
            continue

        analysis = run_dashboard_analysis(product_id, current_seller_id)
        response.append(
            {
                "product_id": product_id,
                "product_name": product.get("product_name", product_id),
                "return_signal": analysis.get("return_signal", "Low"),
                "primary_pattern": (analysis.get("patterns") or ["No strong pattern detected"])[0],
                "summary": analysis.get("summary", "No summary available."),
            }
        )

    return response


@router.get("/product/{product_id}")
def get_product_detail(product_id: str, current_seller_id: str = Depends(get_current_seller)):
    product = products_collection.find_one(
        {"seller_id": current_seller_id, "product_id": product_id},
        {"_id": 0, "product_id": 1, "product_name": 1},
    )

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    analysis = run_dashboard_analysis(product_id, current_seller_id)
    result = {
        "product_id": product_id,
        "product_name": product.get("product_name", product_id),
    }
    result.update(analysis)
    return result
