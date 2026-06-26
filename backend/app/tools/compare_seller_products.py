from bson import ObjectId
from app.database.connection import orders_collection, products_collection, returns_collection, skus_collection


def compare_seller_products(seller_id: str) -> list:
    seller_oid = ObjectId(seller_id)

    products = list(
        products_collection.find(
            {"seller_id": seller_oid},
            {"_id": 1, "product_name": 1},
        )
    )
    if not products:
        return []

    product_ids = [p["_id"] for p in products]

    # Map sku_id -> product_id
    skus = list(skus_collection.find(
        {"product_id": {"$in": product_ids}, "seller_id": seller_oid},
        {"_id": 1, "product_id": 1}
    ))
    sku_to_product = {s["_id"]: s["product_id"] for s in skus}
    sku_ids = list(sku_to_product.keys())

    if not sku_ids:
        return []

    # Orders grouped by sku_id
    order_agg = orders_collection.aggregate([
        {"$match": {"sku_id": {"$in": sku_ids}}},
        {"$group": {"_id": "$sku_id", "order_count": {"$sum": {"$ifNull": ["$quantity", 1]}}}},
    ])
    order_counts_by_product = {}
    for doc in order_agg:
        pid = sku_to_product.get(doc["_id"])
        if pid:
            order_counts_by_product[pid] = order_counts_by_product.get(pid, 0) + doc["order_count"]

    # Returns grouped by sku_id
    return_agg = returns_collection.aggregate([
        {"$match": {"sku_id": {"$in": sku_ids}}},
        {"$group": {"_id": "$sku_id", "return_count": {"$sum": 1}}},
    ])
    return_counts_by_product = {}
    for doc in return_agg:
        pid = sku_to_product.get(doc["_id"])
        if pid:
            return_counts_by_product[pid] = return_counts_by_product.get(pid, 0) + doc["return_count"]

    results = []
    for product in products:
        pid = product["_id"]
        orders = order_counts_by_product.get(pid, 0)
        returns = return_counts_by_product.get(pid, 0)
        return_rate = round(returns / orders, 4) if orders else 0.0

        results.append({
            "product_id": str(pid),
            "product_name": product.get("product_name", str(pid)),
            "orders_count": orders,
            "return_count": returns,
            "return_rate": return_rate,
        })

    return sorted(results, key=lambda item: item["return_rate"], reverse=True)


'''result = compare_seller_products("6a2fe450e9ea3728609743bf")
for r in result:
    print(r)'''


















