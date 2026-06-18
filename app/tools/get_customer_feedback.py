from bson import ObjectId
from app.database.connection import feedback_collection


def get_customer_feedback(product_id: str, seller_id: str) -> list:
    return list(
        feedback_collection.find(
            {
                "seller_id": ObjectId(seller_id),
                "product_id": ObjectId(product_id),
            },
            {"_id": 0},
        )
    )