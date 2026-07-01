from bson import ObjectId
from app.database.connection import skus_collection, returns_collection

# NOTE: This tool returns raw time-series data for the chatbot/Gemini to reason over.
# dashboard_scoring.py has its own _monthly_return_trend() which computes a
# trend label and growth rate for the dashboard card. These two produce different
# output shapes intentionally and should not be expected to match.
def get_return_trend(product_id: str, seller_id: str) -> dict:
    skus=skus_collection.find(
        {
        "seller_id": ObjectId(seller_id),
        "product_id": ObjectId(product_id)
        },
        {"_id":1}
    )
    sku_ids=[sku["_id"] for sku in skus]
    if not sku_ids:
        return{
            "product_id":product_id,
            "seller_id":seller_id,
            "has_data":False,
            "trend":[]
        }
    
    pipeline =[
        {
            "$match":{
                "sku_id":{"$in":sku_ids}
            }
        },
        {
            "$group":{
                "_id":{
                    "year": {"$year":"$return_date"},
                    "month": {"$month":"$return_date"}
                },
                "return_count": {"$sum":1},
                "reasons": {"$push":"$return_reason_category"}
            }
        },
        {
            "$sort":{
                "_id.year":1,
                "_id.month":1
            }
        }
    ]
    results=list(returns_collection.aggregate(pipeline))

    if not results:
        return{
            "product_id":product_id,
            "seller_id":seller_id,
            "has_data":False,
            "trend":[]
        }
    
    trend=[]
    for r in results:
        year=r["_id"]["year"]
        month=r["_id"]["month"]

        reason_counts={}
        for reason in r["reasons"]:
            reason_counts[reason]=reason_counts.get(reason,0)+1
        trend.append({
           "period":f"{year}-{month:02d}",
           "return_count":r["return_count"],
           "reasons":reason_counts
        })
    return{
            "product_id":product_id,
            "seller_id":seller_id,
            "has_data":True,
            "trend":trend
        }


'''import json
result = get_return_trend("6a2fe450e9ea3728609743bf", "6a2fe450e9ea3728609743c4")
print(json.dumps(result, indent=2))'''

