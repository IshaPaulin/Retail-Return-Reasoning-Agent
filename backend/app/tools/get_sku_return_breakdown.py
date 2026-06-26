from bson import ObjectId
from app.database.connection import returns_collection, skus_collection


def get_sku_return_breakdown(product_id: str, seller_id: str) -> list:
    sku_docs = list(skus_collection.find(
        {
            "seller_id": ObjectId(seller_id),
            "product_id": ObjectId(product_id),
        },
        {"_id": 1, "variant_attributes": 1}
    ))

    if not sku_docs:
        return []

    sku_ids = [s["_id"] for s in sku_docs]
    sku_variant_map = {s["_id"]: s.get("variant_attributes") for s in sku_docs}

    pipeline = [
        {
            "$match": {
                "sku_id": {"$in": sku_ids}
            }
        },
        {
            "$group": {
                "_id": "$sku_id",
                "return_count": {"$sum": 1}
            }
        },
        {
            "$project": {
                "_id": 0,
                "sku_id": "$_id",
                "return_count": 1
            }
        }
    ]

    results = list(returns_collection.aggregate(pipeline))

    for r in results:
        v = sku_variant_map.get(r["sku_id"])
        if isinstance(v, dict):
            r["variant"] = ", ".join(f"{k}: {val}" for k, val in v.items())
        else:
            r["variant"] = ""

    return results

'''result=get_sku_return_breakdown("6a2fe450e9ea3728609743c4", "6a2fe450e9ea3728609743bf")
for r in result:
    print(r)'''