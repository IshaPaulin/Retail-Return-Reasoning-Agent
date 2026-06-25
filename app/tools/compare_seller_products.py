from collections import defaultdict

from app.database.connection import products_collection, returns_collection, skus_collection
from app.tools._mongo_helpers import to_object_id


def compare_seller_products(seller_id: str) -> list:
    seller_key = to_object_id(seller_id)
    products = list(
        products_collection.find(
            {"seller_id": seller_key},
            {"_id": 1, "product_name": 1, "name": 1},
        )
    )

    if not products:
        return []

    return_counts = defaultdict(int)
    total_orders_by_product = defaultdict(int)

    for product in products:
        product_id = product.get("_id")
        if not product_id:
            continue

        sku_ids = [
            sku_id
            for sku_id in skus_collection.distinct(
                "_id",
                {
                    "seller_id": seller_key,
                    "product_id": product_id,
                },
            )
        ]

        total_orders_by_product[product_id] = returns_collection.count_documents({"sku_id": {"$in": sku_ids}}) if sku_ids else 0

    for product_id, count in total_orders_by_product.items():
        return_counts[product_id] = count

    results = []
    for product in products:
        product_id = product.get("_id")
        if not product_id:
            continue

        return_count = return_counts.get(product_id, 0)
        product_name = product.get("product_name") or product.get("name") or str(product_id)
        results.append(
            {
                "product_id": str(product_id),
                "product_name": product_name,
                "return_count": return_count,
                "return_rate": None,
            }
        )

    return results
