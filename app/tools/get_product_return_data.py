from bson import ObjectId
from app.database.connection import returns_collection


def get_product_return_data(product_id: str, seller_id: str) -> list:
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
            }
        },
        {"$project": {"_id": 0, "sku_info": 0}},
    ]
    return list(returns_collection.aggregate(pipeline))