from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database.connection import returns_collection, skus_collection
from app.tools._mongo_helpers import to_object_id


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value

    value_str = str(value or "").strip()
    if not value_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value_str, fmt)
        except ValueError:
            continue
    return None


def get_return_trend(product_id: str, seller_id: str) -> dict[str, Any]:
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
        return {
            "has_data": False,
            "trend": [],
            "reason_counts": {},
        }

    records = list(
        returns_collection.find(
            {"sku_id": {"$in": sku_ids}},
            {"_id": 0, "return_reason": 1, "return_date": 1, "order_date": 1, "created_at": 1},
        )
    )

    if not records:
        return {
            "has_data": False,
            "trend": [],
            "reason_counts": {},
        }

    monthly_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}

    for record in records:
        return_reason = record.get("return_reason") or record.get("return_reason_category") or "Unknown"
        reason_counts[str(return_reason)] = reason_counts.get(str(return_reason), 0) + 1

        date = _parse_date(record.get("return_date"))
        if date is None:
            date = _parse_date(record.get("order_date"))
        if date is None:
            date = _parse_date(record.get("created_at"))

        if date is not None:
            period = date.strftime("%Y-%m")
            monthly_counts[period] = monthly_counts.get(period, 0) + 1

    trend = [
        {"period": period, "return_count": monthly_counts[period]}
        for period in sorted(monthly_counts)
    ]

    return {
        "has_data": bool(trend),
        "trend": trend,
        "reason_counts": reason_counts,
    }
