import json
import os
from pathlib import Path

from pymongo import ASCENDING, MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("MONGO_URI")
db_name = os.getenv("DB_NAME", "retail_return_db")

if not uri:
    raise RuntimeError("MONGO_URI is not set")

client = MongoClient(uri, server_api=ServerApi('1'))
db = client[db_name]

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "synthetic"

sellers_collection = db["sellers"]
legacy_sellers_collection = db["seller"]
products_collection = db["products"]
orders_collection = db["orders"]
returns_collection = db["returns"]
feedback_collection = db["feedback"]
skus_collection = db["skus"]
categories_collection = db["categories"]


def _seed_collection(collection, file_name: str) -> None:
    file_path = DATA_DIR / file_name
    if not file_path.exists() or collection.count_documents({}) > 0:
        return

    with file_path.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    if isinstance(data, dict):
        data = data.get("data", [])

    if data:
        collection.insert_many(data)


def _ensure_indexes() -> None:
    sellers_collection.create_index([("username", ASCENDING)], unique=True)
    legacy_sellers_collection.create_index([("username", ASCENDING)], unique=True)
    products_collection.create_index([("seller_id", ASCENDING)])
    products_collection.create_index([("product_id", ASCENDING)])
    orders_collection.create_index([("seller_id", ASCENDING)])
    orders_collection.create_index([("product_id", ASCENDING)])
    returns_collection.create_index([("seller_id", ASCENDING)])
    returns_collection.create_index([("product_id", ASCENDING)])
    feedback_collection.create_index([("seller_id", ASCENDING)])
    feedback_collection.create_index([("product_id", ASCENDING)])
    skus_collection.create_index([("seller_id", ASCENDING)])
    skus_collection.create_index([("product_id", ASCENDING)])
    categories_collection.create_index([("seller_id", ASCENDING)])


def initialize_database() -> None:
    client.admin.command("ping")
    _ensure_indexes()

    _seed_collection(sellers_collection, "sellers.json")
    _seed_collection(products_collection, "products.json")
    _seed_collection(categories_collection, "categories.json")
    _seed_collection(skus_collection, "skus.json")
    _seed_collection(orders_collection, "orders.json")
    _seed_collection(returns_collection, "returns.json")
    _seed_collection(feedback_collection, "feedback.json")
