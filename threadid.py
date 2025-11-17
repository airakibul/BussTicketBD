from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import uuid
import os

# ==========================
# Environment Setup
# ==========================
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["BussTicketBD"]
chat_collection = db["chat_memory"]

# ==========================
# Schema
# ==========================
class ThreadCreateRequest(BaseModel):
    user_id: str

class ThreadCreateResponse(BaseModel):
    thread_id: str

# ==========================
# Service
# ==========================
def create_thread_service(user_id: str):
    thread_id = str(uuid.uuid4())

    chat_collection.insert_one({
        "thread_id": thread_id,
        "user_id": user_id,
        "chat": [],
        "created_at": datetime.utcnow(),
    })

    return thread_id

# ==========================
# Endpoint
# ==========================
app = FastAPI()

@app.post("/create-thread", response_model=ThreadCreateResponse)
def create_thread(payload: ThreadCreateRequest):
    thread_id = create_thread_service(payload.user_id)
    return {"thread_id": thread_id}


