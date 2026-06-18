from app.database.connection import returns_collection


def get_return_reasons_breakdown(product_id: str, seller_id: str) -> dict:
    pipeline = [
        {
            "$match": {
                "seller_id": seller_id,
                "product_id": product_id,
                "return_reason": {"$exists": True, "$ne": None},
            }
        },
        {
            "$group": {
                "_id": "$return_reason",
                "count": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "reason": "$_id",
                "count": 1,
            }
        },
    ]

    results = list(returns_collection.aggregate(pipeline))
    return {item["reason"]: item["count"] for item in results}