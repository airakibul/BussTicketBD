import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv
from openai import OpenAI
from langgraph.graph import StateGraph, END
from pinecone import Pinecone

# =======================
# ENV + CLIENTS
# =======================
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = mongo["BussTicketBD"]
chat_collection = db["chat_memory"]
bus_collection = db["busses"]
tickets_collection = db["tickets"]

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX")
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

# =======================
# FASTAPI APP
# =======================
app = FastAPI()

# =======================
# Pydantic Models
# =======================
class ChatRequest(BaseModel):
    user_id: str
    message: str
    thread_id: Optional[str] = None

class ChatStateSchema(BaseModel):
    user_id: str
    user_message: str
    origin: Optional[str] = None
    destination: Optional[str] = None
    date: Optional[str] = None
    seat: Optional[int] = None

# =======================
# UTILITY FUNCTIONS
# =======================
def get_bus_data():
    return bus_collection.find_one({}, {"_id": 0, "districts": 1, "bus_providers": 1})

def get_user_chat_history(user_id: str, thread_id: Optional[str] = None):
    query = {"user_id": user_id}
    if thread_id:
        query["thread_id"] = thread_id
    doc = chat_collection.find_one(query)
    if doc:
        return doc.get("chat", [])
    return []

def save_chat(user_id: str, message: str, response: str, thread_id: Optional[str] = None):
    if not thread_id:
        thread_id = str(uuid.uuid4())

    chat_collection.update_one(
        {"user_id": user_id, "thread_id": thread_id},
        {"$push": {
            "chat": {
                "user": message,
                "bot": response,
                "timestamp": datetime.utcnow()
            }
        },
         "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True
    )
    return thread_id

# =======================
# STATE FUNCTIONS
# =======================
def book_ticket_state(state, thread_id: Optional[str] = None):
    msg = state.user_message
    chat_history = get_user_chat_history(state.user_id, thread_id)
    bus_data = get_bus_data()

    prompt = f"""
    You are a bus booking assistant.

    User message: {msg}
    Previous conversation: {chat_history}
    Bus data: {bus_data}

    TASK:
    1. Identify missing info: origin, destination, date, seat.
    2. Ask user for missing info if not provided.
    3. If all info is present, respond with JSON: {{ "booking_confirmed": true, "details": ... }}
    4. Otherwise, ask only for missing fields.
    """

    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    response_text = resp.choices[0].message.content

    # Save ticket if confirmed
    if "booking_confirmed" in response_text.lower():
        tickets_collection.insert_one({
            "ticket_id": str(uuid.uuid4()),
            "user_id": state.user_id,
            "details": response_text,
            "timestamp": datetime.utcnow()
        })

    save_chat(state.user_id, msg, response_text, thread_id)
    return response_text

# =======================
# LANGGRAPH STATE SCHEMA
# =======================
states = {"book_ticket": book_ticket_state}
graph = StateGraph(
    state_schema=ChatStateSchema,
    states=states,
    start_state="book_ticket",
    end_state=END
)

# =======================
# FASTAPI ENDPOINT
# =======================
@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        class ChatState:
            def __init__(self, user_id, user_message):
                self.user_id = user_id
                self.user_message = user_message
                self.origin = None
                self.destination = None
                self.date = None
                self.seat = None

        state = ChatState(request.user_id, request.message)
        response = book_ticket_state(state, thread_id=request.thread_id)

        return {"response": response, "thread_id": request.thread_id or str(uuid.uuid4())}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
