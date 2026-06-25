from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient
from pymongo.server_api import ServerApi
import os


print("Starting MongoDB check...")

uri = os.getenv("MONGO_URI")
if not uri:
    raise RuntimeError("MONGO_URI is not set in .env")

client = MongoClient(uri, server_api=ServerApi("1"))
db = client["Retail-Return"]

print("Database:", db.name)
print("Collections:", db.list_collection_names())

seller = db["seller"].find_one({"username": "seller_01"})
print("SELLER:", seller)

if seller:
    seller_id = seller.get("seller_id") or str(seller.get("_id"))
    print("SELLER_ID:", seller_id)

    products_by_string = list(db["products"].find({"seller_id": seller_id}, {"_id": 0}))
    products_by_object_id = list(db["products"].find({"seller_id": seller.get("_id")}, {"_id": 0}))
    products_by_username = list(db["products"].find({"username": "seller_01"}, {"_id": 0}))

    print("PRODUCT COUNT (seller_id as string):", len(products_by_string))
    print("PRODUCT COUNT (seller_id as ObjectId):", len(products_by_object_id))
    print("PRODUCT COUNT (username field):", len(products_by_username))

    if products_by_string:
        print("SAMPLE PRODUCT (string match):", products_by_string[0])
    elif products_by_object_id:
        print("SAMPLE PRODUCT (ObjectId match):", products_by_object_id[0])
    elif products_by_username:
        print("SAMPLE PRODUCT (username match):", products_by_username[0])
    else:
        sample_product = db["products"].find_one()
        print("NO DIRECT MATCH FOUND. SAMPLE PRODUCT:", sample_product)
        if sample_product:
            print("SAMPLE PRODUCT KEYS:", list(sample_product.keys()))

    returns_by_string = list(db["returns"].find({"seller_id": seller_id}, {"_id": 0}).limit(3))
    returns_by_object_id = list(db["returns"].find({"seller_id": seller.get("_id")}, {"_id": 0}).limit(3))
    print("RETURN COUNT (seller_id as string):", db["returns"].count_documents({"seller_id": seller_id}))
    print("RETURN COUNT (seller_id as ObjectId):", db["returns"].count_documents({"seller_id": seller.get("_id")}))
    if returns_by_string:
        print("SAMPLE RETURNS (string):", returns_by_string)
    if returns_by_object_id:
        print("SAMPLE RETURNS (ObjectId):", returns_by_object_id)
else:
    print("seller_01 was not found in the seller collection")