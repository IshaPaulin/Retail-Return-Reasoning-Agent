
from pymongo import MongoClient #MongoClient=python’s connection to MongoDB
from pymongo.server_api import ServerApi #Imports MongoDB Atlas API version support

from dotenv import load_dotenv
import os

load_dotenv()

uri = os.getenv("MONGO_URI") #connection string to connect to atlas ; saved as MONGO_URI in .env

client = MongoClient(uri, server_api=ServerApi('1')) #creates connection python->mongoclient->atlas
# server_api=ServerApi('1')->use stable API Version 1 (for all python connections we use this API)
#without stable API your application could break after an update

# Create database
db = client["Retail-Return"] #Retail-Return is the name of the database ; creates(if database doesn’t exist) or accesses the database Retail-Return


collections = [
    "products",
    "orders",
    "returns",
    "feedback",
    "sku",
    "category"
] #list of collections(tables) to create

for collection in collections:
    if collection not in db.list_collection_names():
        db.create_collection(collection)
        print(f"{collection} created") #prints products created and so on
    else:
        print(f"{collection} already exists")

print("Done")


try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
    print(client.list_database_names())
except Exception as e:
    print(e)

sellers_collection = db["seller"] #storing the collection seller in sellers_collection
products_collection = db["products"]
orders_collection = db["orders"]
returns_collection = db["returns"]
feedback_collection = db["feedback"]
skus_collection = db["sku"]
categories_collection = db["category"]
