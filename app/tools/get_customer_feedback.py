from app.database.connection import feedback_collection
from app.tools._mongo_helpers import to_object_id


def get_customer_feedback(product_id: str, seller_id: str) -> list:
    return list(
        feedback_collection.find(
            {
                "seller_id": to_object_id(seller_id),
                "product_id": to_object_id(product_id),
            },
            {"_id": 0},
        )
    )