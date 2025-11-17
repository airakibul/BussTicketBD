import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from pymongo import MongoClient
from dotenv import load_dotenv
from openai import OpenAI

# ==========================
# Load environment
# ==========================
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ==========================
# MongoDB setup
# ==========================
mongo = MongoClient(MONGO_URI)
db = mongo["BussTicketBD"]
bus_collection = db["busses"]
chat_collection = db["chat_memory"]
booking_collection = db["bookings"]

# ==========================
# OpenAI Client
# ==========================
llm_client = OpenAI(api_key=OPENAI_API_KEY)

# ==========================
# FastAPI setup
# ==========================
app = FastAPI()

# ==========================
# Schemas
# ==========================
class ChatRequest(BaseModel):
    thread_id: str
    message: str

class BookingInfo(BaseModel):
    user_name: str
    from_district: str
    to_district: str
    dropping_point: str
    bus_provider: Optional[str] = None
    date: str

# ==========================
# Helper functions
# ==========================
def get_chat_history(thread_id: str):
    """Retrieve previous chat messages for context."""
    return list(chat_collection.find({"thread_id": thread_id}, {"_id": 0, "message": 1}))

def ask_llm(prompt: str) -> str:
    """Query LLM and return response text."""
    response = llm_client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def validate_district_and_point(from_district, to_district, dropping_point):
    """Ensure district and dropping point exist in bus collection."""
    districts = bus_collection.find_one({}, {"districts": 1})["districts"]
    from_valid = any(d["name"] == from_district for d in districts)
    to_valid = any(d["name"] == to_district for d in districts)
    point_valid = False
    for d in districts:
        if d["name"] == to_district:
            point_valid = any(p["name"] == dropping_point for p in d["dropping_points"])
    return from_valid and to_valid and point_valid

# ==========================
# Main Booking Endpoint
# ==========================
@app.post("/book-ticket/")
def book_ticket(request: ChatRequest):
    # Step 1: Load chat history
    history = get_chat_history(request.thread_id)
    context = "\n".join([msg['message'] for msg in history])
    
    # Step 2: LLM prompt
    prompt = f"""
    You are a bus booking assistant. A user wants to book a ticket. 
    Here is the conversation so far:
    {context}
    User just said: "{request.message}"
    
    Gather the following information if missing: 
    - User Name
    - From District
    - To District
    - Dropping Point
    - Bus Provider (optional)
    - Date of travel
    
    Ask only for missing info. Once all info is collected, confirm the booking with user and return JSON like:
    {{
        "user_name": "...",
        "from_district": "...",
        "to_district": "...",
        "dropping_point": "...",
        "bus_provider": "...",
        "date": "..."
    }}
    """
    
    llm_response = ask_llm(prompt)
    
    # Step 3: Parse JSON from LLM
    try:
        booking_data = json.loads(llm_response)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="LLM response invalid JSON")
    
    # Step 4: Validate districts & dropping point
    valid = validate_district_and_point(
        booking_data["from_district"], 
        booking_data["to_district"], 
        booking_data["dropping_point"]
    )
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid district or dropping point")
    
    # Step 5: Save booking
    booking_collection.insert_one(booking_data)
    
    # Step 6: Return confirmation
    return {"message": "Booking confirmed", "booking": booking_data}

# ==========================
# Chat memory endpoint (optional)
# ==========================
@app.post("/chat/")
def chat(request: ChatRequest):
    """Save chat messages for a thread."""
    chat_collection.insert_one({"thread_id": request.thread_id, "message": request.message})
    return {"message": "Chat saved"}
