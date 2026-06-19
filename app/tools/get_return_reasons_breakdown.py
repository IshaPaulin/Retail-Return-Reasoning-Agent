from bson import ObjectId
from app.database.connection import returns_collection


def get_return_reasons_breakdown(product_id: str, seller_id: str) -> dict:
    pipeline = [
        {"$match": {"sku_id": {"$exists": True, "$ne": None}}},
        {
            "$lookup": {
                "from": "sku",
                "localField": "sku_id",
                "foreignField": "_id",
                "as": "sku_info",
            }
        },
        {"$unwind": "$sku_info"},
        {
            "$match": {
                "sku_info.product_id": ObjectId(product_id),
                "sku_info.seller_id": ObjectId(seller_id),
                "return_reason": {"$exists": True, "$ne": None},
            }
        },
        {"$group": {"_id": "$return_reason", "count": {"$sum": 1}}},
        {"$project": {"_id": 0, "reason": "$_id", "count": 1}},
    ]

    results = list(returns_collection.aggregate(pipeline))
    return {item["reason"]: item["count"] for item in results}

'''result=get_return_reasons_breakdown("6a2fe450e9ea3728609743c4", "6a2fe450e9ea3728609743bf")
for r in result:
    print(r)'''