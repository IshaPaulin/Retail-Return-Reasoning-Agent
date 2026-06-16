
from pymongo import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://karenteddy2006_db_user:pCBbXRfVtH754pmn@learnmongodb.6mgz9gq.mongodb.net/?appName=LearnMongoDB"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
    print(client.list_database_names())
except Exception as e:
    print(e)