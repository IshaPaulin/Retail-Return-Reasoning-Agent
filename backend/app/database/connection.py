
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from app.core.config import MONGO_URI

# Create a new client and connect to the server
client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
# Create database
db = client["Retail-Return"]

'''
collections = [
    "seller",
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
'''
# Send a ping to confirm a successful connection

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
    print(client.list_database_names())
except Exception as e:
    print(e)


sellers_collection = db["seller"]
products_collection = db["products"]
orders_collection = db["orders"]
returns_collection = db["returns"]
feedback_collection = db["feedback"]
skus_collection = db["sku"]
categories_collection = db["category"]
