from bson import ObjectId
from app.database.connection import returns_collection, skus_collection


def get_product_return_data(product_id: str, seller_id: str) -> list:
    sku_docs = list(skus_collection.find(
        {
            "seller_id": ObjectId(seller_id),
            "product_id": ObjectId(product_id),
        },
        {"_id": 1}
    ))
    sku_ids = [s["_id"] for s in sku_docs]

    if not sku_ids:
        return []

    return list(returns_collection.find(
        {"sku_id": {"$in": sku_ids}},
        {"_id": 0}
    ))

'''result=get_product_return_data("6a2fe450e9ea3728609743c4", "6a2fe450e9ea3728609743bf")
for r in result:
    print(r)'''