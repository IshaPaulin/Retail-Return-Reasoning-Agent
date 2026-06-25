from collections import defaultdict

from app.database.connection import returns_collection, skus_collection
from app.tools._mongo_helpers import to_object_id


def get_sku_return_breakdown(product_id: str, seller_id: str) -> list:
    sku_docs = list(
        skus_collection.find(
            {
                "seller_id": to_object_id(seller_id),
                "product_id": to_object_id(product_id),
            },
            {"_id": 1, "variant_attributes": 1, "sku_code": 1},
        )
    )

    if not sku_docs:
        return []

    sku_ids = [sku["_id"] for sku in sku_docs]
    records = list(
        returns_collection.find(
            {"sku_id": {"$in": sku_ids}},
            {"_id": 0, "sku_id": 1},
        )
    )

    if not records:
        return []

    breakdown = defaultdict(int)
    variants = {sku["_id"]: sku.get("variant_attributes") or {} for sku in sku_docs}

    for record in records:
        sku_id = record.get("sku_id")
        if not sku_id:
            continue

        breakdown[sku_id] += 1

    return [
        {
            "sku_id": sku_id,
            "variant": ", ".join(f"{key}: {value}" for key, value in (variants.get(sku_id) or {}).items()),
            "return_count": count,
        }
        for sku_id, count in breakdown.items()
    ]
