from collections import defaultdict
from datetime import datetime

from app.database.connection import returns_collection


def _parse_date(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for date_format in (
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%d-%m-%Y",
            "%m/%d/%Y",
        ):
            try:
                return datetime.strptime(value[:26], date_format)
            except ValueError:
                continue
    return None


def detect_anomalies(product_id: str, seller_id: str) -> dict:
    records = list(
        returns_collection.find(
            {
                "seller_id": seller_id,
                "product_id": product_id,
                "return_date": {"$exists": True, "$ne": None},
            },
            {"_id": 0, "return_date": 1},
        )
    )

    if not records:
        return {"anomalies_detected": False, "details": []}

    buckets = defaultdict(int)
    for record in records:
        parsed_date = _parse_date(record.get("return_date"))
        if parsed_date is None:
            continue
        bucket_key = parsed_date.strftime("%Y-%m")
        buckets[bucket_key] += 1

    if not buckets:
        return {"anomalies_detected": False, "details": []}

    counts = list(buckets.values())
    average_count = sum(counts) / len(counts)
    details = []

    for bucket, count in sorted(buckets.items()):
        if average_count > 0 and count >= average_count * 2:
            details.append(f"Spike in {bucket}: {count} returns")

    return {
        "anomalies_detected": len(details) > 0,
        "details": details,
    }
