import os
from dotenv import load_dotenv
from pymongo import MongoClient
from openai import OpenAI
from pinecone import Pinecone

# Load environment variables
load_dotenv()

# OpenAI
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

# MongoDB
MONGO_URI = os.getenv("MONGO_URI","mongodb://localhost:27017")
mongo = MongoClient(MONGO_URI)
db = mongo["BussTicketBD"]
bus_collection = db["busses"]
chat_collection = db["chat_memory"]

# Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX")
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME) 

__all__ = [
    "client",
    "bus_collection",
    "chat_collection",
    "index",
]
