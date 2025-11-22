import os
from dotenv import load_dotenv
from pymongo import MongoClient
from openai import OpenAI

load_dotenv()

# OpenAI
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

# MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo = MongoClient(MONGO_URI)
db = mongo["BussTicketBD"]

bus_collection = db["busses"]
chat_collection = db["chat_memory"]

__all__ = [
    "client",
    "bus_collection",
    "chat_collection",
]
