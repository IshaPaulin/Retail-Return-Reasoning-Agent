import math
from datetime import datetime
from app.database import db


def detect_anomalies(product_id: str, seller_id: str) -> dict:
    """
    Detects unusual patterns for a product:
    1. Sudden volume spikes or drops over a time-series window.
    2. Concentrated reason clusters (e.g., if one reason significantly outweighs historical norms).
    """
    # Fetch all relevant return records
    cursor = list(db["returns"].find(
        {"seller_id": seller_id, "product_id": product_id},
        {"return_date": 1, "return_reason": 1}
    ))

    if not cursor or len(cursor) < 5:
        return {
            "anomalies_detected": False,
            "details": ["Insufficient data points to perform anomaly or cluster detection."]
        }

    anomalies_detected = False
    details = []

    # -------------------------------------------------------------------------
    # PART 1: TIME-SERIES ANOMALY DETECTION (Spikes / Drops)
    # -------------------------------------------------------------------------
    weekly_counts = {}
    reason_counts = {}
    total_returns = 0

    for record in cursor:
        reason = record.get("return_reason")
        date_str = record.get("return_date")

        # Track categories
        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            total_returns += 1

        # Track time series (Grouping by ISO-8601 Year and Week Number)
        if date_str:
            try:
                date_obj = datetime.fromisoformat(date_str.replace("Z", ""))
                year_week = date_obj.strftime("%Y-W%W")
                weekly_counts[year_week] = weekly_counts.get(year_week, 0) + 1
            except Exception:
                continue

    # Analyze weekly volumes if we have at least 4 distinct weeks of data
    if len(weekly_counts) >= 4:
        counts = list(weekly_counts.values())
        mean_vol = sum(counts) / len(counts)
        variance = sum((x - mean_vol) ** 2 for x in counts) / len(counts)
        std_dev = math.sqrt(variance)

        if std_dev > 0:
            threshold = 1.75  # Z-score threshold for alert flag
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

    # -------------------------------------------------------------------------
    # PART 2: CATEGORICAL CLUSTER DETECTION (Reason Concentration)
    # -------------------------------------------------------------------------
    # If a single return reason accounts for more than 55% of all returns,
    # it indicates a highly concentrated issue (e.g., a bad manufacturing batch or sizing chart error).
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
