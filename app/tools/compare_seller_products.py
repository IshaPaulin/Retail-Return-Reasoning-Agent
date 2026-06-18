from app.database.connection import orders_collection, products_collection, returns_collection


def compare_seller_products(seller_id: str) -> list:
    products = list(
        products_collection.find(
            {"seller_id": seller_id},
            {"_id": 0, "product_id": 1, "product_name": 1},
        )
    )

    if not products:
        return []

    product_ids = [product["product_id"] for product in products if product.get("product_id")]
    if not product_ids:
        return []

    order_counts = {
        doc["_id"]: doc["order_count"]
        for doc in orders_collection.aggregate(
            [
                {"$match": {"seller_id": seller_id, "product_id": {"$in": product_ids}}},
                {"$group": {"_id": "$product_id", "order_count": {"$sum": 1}}},
            ]
        )
    }

    return_counts = {
        doc["_id"]: doc["return_count"]
        for doc in returns_collection.aggregate(
            [
                {"$match": {"seller_id": seller_id, "product_id": {"$in": product_ids}}},
                {"$group": {"_id": "$product_id", "return_count": {"$sum": 1}}},
            ]
        )
    }

    results = []
    for product in products:
        product_id = product.get("product_id")
        if not product_id:
            continue

        orders = order_counts.get(product_id, 0)
        returns = return_counts.get(product_id, 0)
        return_rate = round((returns / orders) * 100, 2) if orders else 0.0

        results.append(
            {
                "product_id": product_id,
                "product_name": product.get("product_name", product_id),
                "orders_count": orders,
                "return_count": returns,
                "return_rate": return_rate,
            }
        )

    return sorted(results, key=lambda item: item["return_rate"], reverse=True)
