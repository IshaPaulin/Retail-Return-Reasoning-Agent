from bson import ObjectId
from backend.app.database.connection import returns_collection


def get_sku_return_breakdown(product_id: str, seller_id: str) -> list:
    pipeline = [
        {"$match": {"sku_id": {"$exists": True, "$ne": None}}},
        {
            "$lookup": {
                "from": "sku",  # confirm actual collection name in connection.py
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
            }
        },
        {
            "$group": {
                "_id": "$sku_id",
                "variant_attributes": {"$first": "$sku_info.variant_attributes"},
                "return_count": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "sku_id": "$_id",
                "variant": "$variant_attributes",
                "return_count": 1,
            }
        },
    ]

    results = list(returns_collection.aggregate(pipeline))

    for r in results:
        v = r.get("variant")
        if isinstance(v, dict):
            r["variant"] = ", ".join(f"{k}: {val}" for k, val in v.items())
        elif v is None:
            r["variant"] = ""

    return results

'''result=get_sku_return_breakdown("6a2fe450e9ea3728609743c4", "6a2fe450e9ea3728609743bf")
for r in result:
    print(r)'''