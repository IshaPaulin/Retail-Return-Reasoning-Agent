from app.database.connection import returns_collection


def get_product_return_data(product_id: str, seller_id: str) -> list:
    return list(
        returns_collection.find(
            {
                "seller_id": seller_id,
                "product_id": product_id,
            },
            {"_id": 0},
        )
    )
