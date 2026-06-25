from app.database.connection import returns_collection, skus_collection
from app.tools._mongo_helpers import to_object_id


def get_return_reasons_breakdown(product_id: str, seller_id: str) -> dict:
    sku_ids = [
        sku_id
        for sku_id in skus_collection.distinct(
            "_id",
            {
                "seller_id": to_object_id(seller_id),
                "product_id": to_object_id(product_id),
            },
        )
    ]

    if not sku_ids:
        return {}

    pipeline = [
        {
            "$match": {
                "sku_id": {"$in": sku_ids},
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

