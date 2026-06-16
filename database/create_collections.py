from pymongo import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://karenteddy2006_db_user:pCBbXRfVtH754pmn@learnmongodb.6mgz9gq.mongodb.net/?appName=LearnMongoDB"

client = MongoClient(uri, server_api=ServerApi('1'))

# Create database
db = client["Retail-Return"]

collections = [
    "products",
    "orders",
    "returns",
    "feedback",
    "sku",
    "category"
]

for collection in collections:
    if collection not in db.list_collection_names():
        db.create_collection(collection)
        print(f"{collection} created")
    else:
        print(f"{collection} already exists")

print("Done")
