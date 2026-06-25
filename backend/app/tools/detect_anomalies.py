import math
from datetime import datetime
from bson import ObjectId

from app.database.connection import db


def detect_anomalies(product_id: str, seller_id: str) -> dict:
    """
    Detects unusual patterns for a product:
    1. Sudden volume spikes or drops over a time-series window.
    2. Concentrated reason clusters (using return_reason_category).
    """
    try:
        # Convert incoming string IDs to ObjectIds for MongoDB matching
        prod_obj_id = ObjectId(product_id)
        sel_obj_id = ObjectId(seller_id)
    except Exception:
        return {
            "anomalies_detected": False,
            "details": ["Invalid product_id or seller_id format."]
        }

    # FIX BUG 2: Resolve schema decoupling by fetching SKU IDs first
    sku_ids = [
        s["_id"] for s in db["sku"].find(
            {"product_id": prod_obj_id, "seller_id": sel_obj_id},
            {"_id": 1}
        )
    ]

    if not sku_ids:
        return {
            "anomalies_detected": False,
            "details": ["No matching SKUs found for this product under your account."]
        }

    cursor = list(db["returns"].find(
        {"sku_id": {"$in": sku_ids}},
        {"return_date": 1, "return_reason_category": 1}
    ))

    if not cursor or len(cursor) < 5:
        return {
            "anomalies_detected": False,
            "details": ["Insufficient historical timeline data to accurately identify anomalies."]
        }

    anomalies_detected = False
    details = []

    weekly_counts = {}
    reason_counts = {}
    total_returns = 0

    for record in cursor:

        reason = record.get("return_reason_category")

        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            total_returns += 1

        # FIX BUG 3: Use direct native Python datetime object returned from PyMongo
        date_obj = record.get("return_date")
        if isinstance(date_obj, datetime):
            try:
                year_week = date_obj.strftime("%Y-W%W")
                weekly_counts[year_week] = weekly_counts.get(year_week, 0) + 1
            except Exception:
                continue

    # -------------------------------------------------------------------------
    # PART 1: TIME-SERIES ANOMALY DETECTION (Spikes / Drops)
    # -------------------------------------------------------------------------
    if len(weekly_counts) >= 4:
        counts = list(weekly_counts.values())
        mean_vol = sum(counts) / len(counts)
        variance = sum((x - mean_vol) ** 2 for x in counts) / len(counts)
        std_dev = math.sqrt(variance)

        if std_dev > 0:
            threshold = 1.75
            for week, count in sorted(weekly_counts.items()):
                z_score = (count - mean_vol) / std_dev
                if z_score > threshold:
                    anomalies_detected = True
                    details.append(
                        f"Sudden Volume Spike in {week}: Recorded {count} returns (Weekly average: {mean_vol:.1f}).")
                elif z_score < -threshold:
                    anomalies_detected = True
                    details.append(
                        f"Unexpected Drop in {week}: Recorded {count} returns (Weekly average: {mean_vol:.1f}).")


    CLUSTER_THRESHOLD = 0.55
    for reason, count in reason_counts.items():
        concentration_ratio = count / total_returns
        if concentration_ratio >= CLUSTER_THRESHOLD and count >= 3:
            anomalies_detected = True
            percentage = concentration_ratio * 100
            details.append(
                f"Concentrated Reason Cluster: '{reason}' accounts for {percentage:.1f}% "
                f"of all returns for this product ({count}/{total_returns} occurrences)."
            )

    return {
        "anomalies_detected": anomalies_detected,
        "details": details
    }

#print(detect_anomalies("6a2fe450e9ea3728609743c4","6a2fe450e9ea3728609743bf"))
#py -m app.tools.detect_anomalies