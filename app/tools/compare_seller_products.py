from collections import defaultdict

from app.database.connection import products_collection, returns_collection


def compare_seller_products(seller_id: str) -> list:
    products = list(
        products_collection.find(
            {"seller_id": seller_id},
            {"_id": 0, "product_id": 1, "product_name": 1},
        )
    )

    if not products:
        return []

    return_counts = defaultdict(int)
    total_orders_by_product = defaultdict(int)

    for product in products:
        product_id = product.get("product_id")
        if not product_id:
            continue

        total_orders_by_product[product_id] = returns_collection.count_documents(
            {"seller_id": seller_id, "product_id": product_id}
        )

    for product_id, count in total_orders_by_product.items():
        return_counts[product_id] = count

    results = []
    for product in products:
        product_id = product.get("product_id")
        if not product_id:
            continue

        return_count = return_counts.get(product_id, 0)
        product_name = product.get("product_name", product_id)
        results.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "return_count": return_count,
                "return_rate": None,
            }
        )

    return results
