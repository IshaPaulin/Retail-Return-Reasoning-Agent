from app.database.connection import returns_collection, skus_collection
from app.tools._mongo_helpers import to_object_id


def get_product_return_data(product_id: str, seller_id: str) -> list:
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
        return []

    return list(
        returns_collection.find(
            {
                "sku_id": {"$in": sku_ids},
            },
            {"_id": 0},
        )
    )