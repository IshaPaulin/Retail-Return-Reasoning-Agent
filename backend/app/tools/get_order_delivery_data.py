from datetime import datetime
from bson import ObjectId
from app.database.connection import orders_collection, skus_collection

# Statuses where delivery duration is meaningful
DELIVERED_STATUSES = {"delivered", "returned"}

def get_order_delivery_data(product_id: str, seller_id: str) -> list:
    # ------------------------------------------------------------------
    # Step 1: Resolve SKU ids for this product scoped to the seller.
    # ORDER has no seller_id / product_id, so we must join through SKU.
    # SKU carries both seller_id and product_id as indexed FKs.
    # ------------------------------------------------------------------
    sku_docs = list(
        skus_collection.find(
            {
                "seller_id": ObjectId(seller_id),
                "product_id": ObjectId(product_id),
            },
            {"_id": 1},
        )
    )

    if not sku_docs:
        return []

    sku_ids = [doc["_id"] for doc in sku_docs]

    # ------------------------------------------------------------------
    # Step 2: Fetch orders whose sku_id is in the resolved set.
    # Orders without a sku_id (product-level orders) are not reachable
    # through this join — ask DB team whether those exist in the dataset.
    # ------------------------------------------------------------------
    records = list(
        orders_collection.find(
            {"sku_id": {"$in": sku_ids}},
            {
                "_id": 0,
                "customer_id": 1,
                "order_date": 1,
                "delivery_date": 1,
                "fulfilment_status": 1,  # single-l — matches schema exactly
                "quantity": 1,
                "sku_id": 1,
                "price": 1,
            },
        ).sort("order_date", 1)  # oldest → newest for trend analysis
    )

    if not records:
        return []

    for record in records:
        status = record.get("fulfilment_status")
        if status in DELIVERED_STATUSES:
            record["delivery_duration_days"] = _calc_delivery_duration(
                record.get("order_date"), record.get("delivery_date")
            )
        else:
            # pending / shipped / cancelled — duration not meaningful
            record["delivery_duration_days"] = None

    return records

def _calc_delivery_duration(order_date, delivery_date):
    """
    Return calendar days between order_date and delivery_date.
    Both fields are ISODate in Mongo, so they arrive as Python datetime
    objects — _parse_date short-circuits on the isinstance check.
    String parsing is kept as a fallback for JSON-based dev/test data.
    """
    if not order_date or not delivery_date:
        return None

    od = _parse_date(order_date)
    dd = _parse_date(delivery_date)

    if od is None or dd is None:
        return None

    delta = (dd - od).days
    return delta if delta >= 0 else None


def _parse_date(value):
    if isinstance(value, datetime):
        return value  # ISODate from Mongo — no string parsing needed

    DATE_FORMATS = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None

'''result = get_order_delivery_data("6a2fe450e9ea3728609743c4", "6a2fe450e9ea3728609743bf")
for r in result:
    print(r)'''