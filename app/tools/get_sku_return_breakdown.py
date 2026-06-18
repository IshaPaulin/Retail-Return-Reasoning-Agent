from collections import defaultdict

from app.database.connection import returns_collection


def get_sku_return_breakdown(product_id: str, seller_id: str) -> list:
    records = list(
        returns_collection.find(
            {
                "seller_id": seller_id,
                "product_id": product_id,
            },
            {"_id": 0, "sku_id": 1, "variant_attributes": 1},
        )
    )

    if not records:
        return []

    if not any(record.get("sku_id") for record in records):
        return []

    breakdown = defaultdict(int)
    variants = {}

    for record in records:
        sku_id = record.get("sku_id")
        if not sku_id:
            continue

        breakdown[sku_id] += 1
        variant_attributes = record.get("variant_attributes")
        if isinstance(variant_attributes, dict):
            variants[sku_id] = ", ".join(
                f"{key}: {value}" for key, value in variant_attributes.items()
            )
        elif isinstance(variant_attributes, str):
            variants[sku_id] = variant_attributes

    return [
        {
            "sku_id": sku_id,
            "variant": variants.get(sku_id, ""),
            "return_count": count,
        }
        for sku_id, count in breakdown.items()
    ]

