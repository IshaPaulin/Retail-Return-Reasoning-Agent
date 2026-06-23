#This file creates 2 dashboard APIs:
#GET /dashboard/
#GET /dashboard/product/{product_id}

from __future__ import annotations #Allows modern type hints.

import asyncio #Used to run multiple tasks concurrently.
from typing import Any #Type hint for any datatype.

from fastapi import APIRouter, Depends, HTTPException, status
'''
APIRouter-> Creates routes.
Depends-> Dependency injection.
HTTPException-> Returns API errors.
status-> Contains HTTP status codes.
'''
from app.agent.dashboard_pipeline import run_dashboard_analysis, run_product_detail
from app.auth.jwt import validate_token
from app.tools.compare_seller_products import compare_seller_products

router = APIRouter(prefix="/dashboard", tags=["dashboard"]) #tags-->Put all routes in this router under the "dashboard" section in Swagger docs

#router = APIRouter(prefix="/dashboard") -->Every route in this router starts with /dashboard

# ---------------------------------------------------------------------------
# GET /dashboard/
# Returns one card per product for the authenticated seller.
# ---------------------------------------------------------------------------
'''
@router.get("/"): adds the route-specific path.

So FastAPI combines:
prefix      = /dashboard
route path  = /
So result=prefix+path

Result:GET /dashboard/

Another example:
@router.get("/product/{product_id}")

FastAPI combines:
prefix = /dashboard
path   = /product/{product_id}
Result:GET /dashboard/product/{product_id}
'''
@router.get("/", response_model=dict) 
async def get_dashboard(seller_id: str = Depends(validate_token)) -> dict[str, Any]: #calls fn validate_token to make sure its the loggedin seller
    """
    Triggers the agent pipeline for every product belonging to the seller
    and returns a list of product cards for the dashboard view.

    Each card contains:
        product_id, product_name, return_rate, orders_count, return_count,
        avg_rating, anomaly, anomaly_message, risk_signal, error
    """
    # Step 1 — fetch all products for this seller in one DB round-trip
    try:
        products: list[dict] = compare_seller_products(seller_id=seller_id) #gets all the pdts (product ids) of tht seller
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch product list: {exc}",
        )

    if not products: #if seller doesnt hv any products
        return {"seller_id": seller_id, "products": []}

    # Step 2 — run analysis for every product concurrently
    loop = asyncio.get_event_loop() #for concurrent execution

    async def analyse_one(product: dict) -> dict[str, Any]: #Analyzes one product.
        product_id = str(product.get("product_id", "")) #extract product id
        if not product_id: #Missing ID ->Returns error.
            return {"error": "Missing product_id in compare_seller_products result"}
        try:
            return await loop.run_in_executor(
                None,
                lambda: run_dashboard_analysis(
                    product_id=product_id,
                    seller_id=seller_id,
                    product=product, #Passes already-fetched product data.
                    include_gemini=True, #Runs Gemini risk classification.
                ),
            ) #calls dashboard_pipeline:Anomaly Detection,Risk Analysis,Metrics Calculation

        except Exception as exc:
            return {
                "product_id":      product_id,
                "product_name":    product.get("product_name", "Unknown Product"),
                "return_rate":     product.get("return_rate", 0.0),
                "orders_count":    product.get("orders_count", 0),
                "return_count":    product.get("return_count", 0),
                "avg_rating":      product.get("avg_rating", None),
                "anomaly":         False,
                "anomaly_message": None,
                "risk_signal":     "Unknown",
                "error":           str(exc),
            }

    cards = await asyncio.gather(*[analyse_one(p) for p in products])
    '''
    suppose: products = [P1,P2,P3]
    Runs:analyse_one(P1),analyse_one(P2),analyse_one(P3) simultaneously.
    '''

    return {
        "seller_id": seller_id,
        "products":  list(cards),
    }


# ---------------------------------------------------------------------------
# GET /dashboard/product/{product_id}
# Returns the full drill-down detail for a single product.
# ---------------------------------------------------------------------------

@router.get("/product/{product_id}", response_model=dict)
async def get_product_detail(
    product_id: str,
    seller_id: str = Depends(validate_token),
) -> dict[str, Any]:
    """
    Runs the full detail pipeline for one product and returns structured
    insight sections:
        overview, return_trend, return_reasons, customer_feedback,
        delivery, anomalies, sku_breakdown

    Sections with no available data are marked available=False and omitted
    by the frontend.
    """
    loop = asyncio.get_event_loop()

    try:
        detail = await loop.run_in_executor(
            None,
            lambda: run_product_detail(
                product_id=product_id,
                seller_id=seller_id,
            ),
        ) #calls pipeline
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Product detail analysis failed: {exc}",
        )

    # Guard: make sure this product actually belongs to the seller.
    # run_product_detail already scopes every tool call by seller_id, so if
    # overview data came back empty for a valid product_id it just means no
    # data exists — not an auth violation.  A missing product returns an
    # empty overview; we surface that as 404 only when orders AND returns
    # are both zero AND no other section has data.
    sections_with_data = [
        k for k, v in detail.items()
        if isinstance(v, dict) and v.get("available")
    ] #this checks:overview.available,delivery.available,anomalies.available
    if not sections_with_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No data found for product '{product_id}' under your account. "
                "Verify the product ID belongs to your seller account."
            ),
        )

    return detail #returns to frontend

'''
Flow:
Seller Login
     ↓
JWT token generated
     ↓
Frontend stores token
     ↓
GET /dashboard
     ↓
dashboard.py
     ↓
validate_token()
     ↓
extract seller_id from JWT
     ↓
compare_seller_products()
     ↓
get all seller products
     ↓
run_dashboard_analysis() for each product
     ↓
anomaly detection
risk classification
metrics calculation
     ↓
dashboard.py collects results
     ↓
returns JSON response
     ↓
Frontend displays cards

for product detail:
Frontend clicks product card
     ↓
GET /dashboard/product/P123
     ↓
dashboard.py
     ↓
validate_token
     ↓
run_product_detail()
     ↓
return data
delivery data
feedback
anomalies
sku breakdown
     ↓
dashboard.py
     ↓
JSON response
     ↓
Frontend renders charts/details
'''