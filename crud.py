import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
from openai import OpenAI
from pymongo import MongoClient
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from pinecone import Pinecone
import uuid
from datetime import datetime

# =====================================================
# ENV + CLIENTS
# =====================================================
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = mongo["BussTicketBD"]
bus_collection = db["busses"]
chat_collection = db["chat_memory"]

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX")
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

app = FastAPI()

# =====================================================
# SCHEMAS
# =====================================================
class ChatInput(BaseModel):
    message: str
    user_id: str  # to associate chat with a user
    thread_id: Optional[str] = None  # optional, can create new thread

# =====================================================
# EMBEDDING FUNCTION
# =====================================================
def embed(text: str):
    res = client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return res.data[0].embedding

# =====================================================
# CHAT STATE
# =====================================================
class ChatState(BaseModel):
    user_message: str
    intent: Optional[str] = None
    result: Any = None
    thread_id: Optional[str] = None  # optional, can create new thread

# =====================================================
# INTENT DETECTION
# =====================================================
def detect_intent(state: ChatState):
    chat = chat_collection.find_one({"thread_id": state.thread_id}, {"chat": {"$slice": -10}})

    prompt = f"""
You are a bus ticket booking assistant.

You are given the user's last 10 messages and the assistant's replies:
CHAT_HISTORY:
{chat}

Your job:
1. Read the full chat history and identify what the user is currently trying to do.
2. Use the latest user message to determine the intent in context.

INTENT RULES (choose EXACTLY ONE):
- ask_for_info       → user asks about routes, dropping points, fare, timing, seat availability
- provider_info      → user asks about bus company details
- book_ticket        → user is trying to book/confirm a ticket
- view_ticket        → user wants to see previously booked tickets
- cancel_ticket      → user wants to cancel a ticket

LATEST USER MESSAGE:
{state.user_message}

Output:
Return ONLY the intent name, nothing else.
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    state.intent = resp.choices[0].message.content.strip()
    return state

# =====================================================
# INTENT HANDLERS
# =====================================================
def ask_for_info(state: ChatState):
    msg = state.user_message
    dataset = bus_collection.find_one({}, {"districts": 1, "bus_providers": 1})
    chat = chat_collection.find_one({"thread_id": state.thread_id}, {"chat": {"$slice": -10}})
    prompt = f"""
    You are a bus route search assistant.

    User message:
    {msg}
    
    CHAT HISTORY:
    {chat}

    Data:
    Districts with dropping points:
    {dataset['districts']}

    Bus Providers:
    {dataset['bus_providers']}

    Task:
    - Use the chat history to understand context.
    - Provide accurate info about routes, dropping points, fares, timings, seat availability.
    - Respond with a SHORT natural-language answer, NOT JSON.
    """
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    state.result = resp.choices[0].message.content.strip()
    return state

def provider_info(state: ChatState):
    query = state.user_message
    try:
        vector = embed(query)
        results = index.query(vector=vector, top_k=1, include_metadata=True)
        if not results["matches"]:
            state.result = "No relevant information found for this provider."
            return state

        text_blocks = [match["metadata"].get("text", "") for match in results["matches"]]
        context_str = "\n\n".join(text_blocks)

        prompt = f"""
Use the following context to answer the user query.

Context:
{context_str}

User Query:
{query}

Answer:
"""
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Answer based only on the provided context."},
                {"role": "user", "content": prompt}
            ]
        )
        state.result = completion.choices[0].message.content
        return state

    except Exception as e:
        state.result = f"Error: {str(e)}"
        return state
    
def book_ticket(state: ChatState):
    """
    Multi-step booking process:
    1. Extract booking info from chat history
    2. Check for missing fields
    3. If complete, ask for confirmation
    4. If confirmed, save to database
    """
    thread_id = state.thread_id
    user_message = state.user_message.lower()
    
    # Fetch chat history
    chat_doc = chat_collection.find_one(
        {"thread_id": thread_id},
        {"chat": 1, "booking_data": 1}
    )
    
    if not chat_doc:
        state.result = "Sorry, I couldn't find your conversation history."
        return state
    
    chat_history = chat_doc.get("chat", [])
    existing_booking_data = chat_doc.get("booking_data", {})
    
    # Format chat history for LLM
    formatted_history = "\n".join([
        f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}"
        for msg in chat_history[-15:]  # Last 15 messages for context
    ])
    
    # Check if user is confirming the booking
    confirmation_keywords = ["yes", "confirm", "book", "proceed", "ok", "correct", "right", "sure", "definitely"]
    is_confirming = any(keyword in user_message for keyword in confirmation_keywords)
    
    # If booking data exists and user is confirming
    if existing_booking_data.get("awaiting_confirmation") and is_confirming:
        # Save booking to database
        booking_id = str(uuid.uuid4())
        booking_record = {
            "booking_id": booking_id,
            "user_id": existing_booking_data.get("user_id"),
            "name": existing_booking_data.get("name"),
            "phone": existing_booking_data.get("phone"),
            "pickup_point": existing_booking_data.get("pickup_point"),
            "dropping_point": existing_booking_data.get("dropping_point"),
            "date": existing_booking_data.get("date"),
            "seats": existing_booking_data.get("seats"),
            "status": "confirmed",
            "booked_at": datetime.utcnow()
        }
        
        # Insert into bookings collection
        db["bookings"].insert_one(booking_record)
        
        # Clear booking_data from chat collection
        chat_collection.update_one(
            {"thread_id": thread_id},
            {"$unset": {"booking_data": ""}}
        )
        
        state.result = f"""
✅ Booking Confirmed!

Booking ID: {booking_id}
Name: {booking_record['name']}
Phone: {booking_record['phone']}
From: {booking_record['pickup_point']}
To: {booking_record['dropping_point']}
Date: {booking_record['date']}
Seats: {booking_record['seats']}

Your ticket has been successfully booked. You will receive a confirmation shortly.
"""
        return state
    
    # Extract booking information using LLM
    extraction_prompt = f"""
You are a booking assistant. Extract booking information from the conversation.

CHAT HISTORY:
{formatted_history}

CURRENT USER MESSAGE:
{state.user_message}

EXISTING DATA (if any):
{existing_booking_data}

Extract the following information:
- name: Passenger's full name
- phone: Phone number (with country code if provided)
- pickup_point: Pickup location/point
- dropping_point: Dropping location/point
- date: Travel date (format: YYYY-MM-DD)
- seats: Number of seats (as integer)

RULES:
1. Only extract information that is clearly stated
2. Use existing data if the user hasn't provided new information
3. If a field is not mentioned, return null for that field
4. For date, convert natural language (e.g., "tomorrow", "next Monday") to YYYY-MM-DD format
5. Today's date is {datetime.utcnow().strftime('%Y-%m-%d')}

Return ONLY a JSON object with these exact keys:
{{
    "name": "value or null",
    "phone": "value or null",
    "pickup_point": "value or null",
    "dropping_point": "value or null",
    "date": "YYYY-MM-DD or null",
    "seats": number or null
}}
"""
    
    try:
        extraction_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0
        )
        
        # Parse extracted data
        import json
        extracted_text = extraction_response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        if "```json" in extracted_text:
            extracted_text = extracted_text.split("```json")[1].split("```")[0].strip()
        elif "```" in extracted_text:
            extracted_text = extracted_text.split("```")[1].split("```")[0].strip()
        
        booking_data = json.loads(extracted_text)
        
        # Merge with existing data (new data takes precedence)
        for key, value in booking_data.items():
            if value is not None:
                existing_booking_data[key] = value
        
        # Check for missing fields
        required_fields = ["name", "phone", "pickup_point", "dropping_point", "date", "seats"]
        missing_fields = [field for field in required_fields if not existing_booking_data.get(field)]
        
        if missing_fields:
            # Save partial data to MongoDB
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$set": {"booking_data": existing_booking_data}}
            )
            
            # Ask for missing information
            field_prompts = {
                "name": "your full name",
                "phone": "your phone number",
                "pickup_point": "your pickup point",
                "dropping_point": "your dropping point",
                "date": "your travel date",
                "seats": "number of seats you need"
            }
            
            collected_info = "\n".join([
                f"✓ {field.replace('_', ' ').title()}: {existing_booking_data[field]}"
                for field in required_fields if existing_booking_data.get(field)
            ])
            
            missing_info = "\n".join([
                f"✗ {field_prompts[field].title()}"
                for field in missing_fields
            ])
            
            state.result = f"""
I'm collecting your booking information.

📋 Information collected so far:
{collected_info if collected_info else "None yet"}

❓ I still need:
{missing_info}

Please provide the missing information.
"""
            return state
        
        else:
            # All data collected, ask for confirmation
            existing_booking_data["awaiting_confirmation"] = True
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$set": {"booking_data": existing_booking_data}}
            )
            
            state.result = f"""
📋 Please confirm your booking details:

👤 Name: {existing_booking_data['name']}
📞 Phone: {existing_booking_data['phone']}
📍 Pickup Point: {existing_booking_data['pickup_point']}
📍 Dropping Point: {existing_booking_data['dropping_point']}
📅 Date: {existing_booking_data['date']}
💺 Seats: {existing_booking_data['seats']}

Is this information correct? Type 'yes' to confirm or provide corrections.
"""
            return state
    
    except Exception as e:
        state.result = f"Sorry, I encountered an error while processing your booking: {str(e)}"
        return state

def view_ticket(state: ChatState):
    state.result = "User ticket info (placeholder)."
    return state

def cancel_ticket(state: ChatState):
    state.result = "Ticket cancelled (placeholder)."
    return state

# =====================================================
# LANGGRAPH SETUP
# =====================================================
graph = StateGraph(ChatState)
graph.add_node("detect_intent", detect_intent)
graph.add_node("ask_for_info", ask_for_info)
graph.add_node("provider_info", provider_info)
graph.add_node("book_ticket", book_ticket)
graph.add_node("view_ticket", view_ticket)
graph.add_node("cancel_ticket", cancel_ticket)
graph.set_entry_point("detect_intent")
graph.add_conditional_edges(
    "detect_intent",
    lambda state: state.intent,
    {
        "ask_for_info": "ask_for_info",
        "provider_info": "provider_info",
        "book_ticket": "book_ticket",
        "view_ticket": "view_ticket",
        "cancel_ticket": "cancel_ticket",
    }
)
for f in ["ask_for_info", "provider_info", "book_ticket", "view_ticket", "cancel_ticket"]:
    graph.add_edge(f, END)
flow = graph.compile()

# =====================================================
# CHAT MEMORY HELPERS
# =====================================================
def create_or_get_thread(user_id: str, thread_id: Optional[str] = None):
    if thread_id:
        thread = chat_collection.find_one({"thread_id": thread_id})
        if thread:
            return thread_id
    # Create new thread
    new_thread_id = str(uuid.uuid4())
    chat_collection.insert_one({
        "thread_id": new_thread_id,
        "user_id": user_id,
        "chat": [],
        "created_at": datetime.utcnow()
    })
    return new_thread_id

def store_message(thread_id: str, user_message: str, bot_response: str):
    chat_collection.update_one(
        {"thread_id": thread_id},
        {"$push": {"chat": {"user": user_message, "bot": bot_response, "timestamp": datetime.utcnow()}}}
    )

# =====================================================
# CHAT ENDPOINT
# =====================================================
@app.post("/chat")
async def chat_endpoint(data: ChatInput):
    # Ensure thread exists
    thread_id = create_or_get_thread(data.user_id, data.thread_id)
    state = {
    "user_message": data.message,
    "thread_id": thread_id
    }

    out = flow.invoke(state)

    # Save chat to MongoDB
    store_message(thread_id, data.message, out["result"])

    return {"thread_id": thread_id, "response": out["result"]}
