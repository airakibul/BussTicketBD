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
    LLM-driven booking process - minimal if/else, maximum LLM intelligence
    """
    import json
    
    thread_id = state.thread_id
    user_message = state.user_message
    
    # Fetch dataset from MongoDB
    dataset = bus_collection.find_one({}, {"districts": 1, "bus_providers": 1})
    if not dataset:
        state.result = "Sorry, the booking system is currently unavailable."
        return state
    
    districts = dataset.get("districts", [])
    bus_providers = dataset.get("bus_providers", [])
    
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
    
    # Format chat history
    formatted_history = "\n".join([
        f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}"
        for msg in chat_history[-15:]
    ])
    
    # Format dataset for LLM
    dataset_info = {
        "districts": districts,
        "bus_providers": bus_providers
    }
    
    # Single LLM call to handle everything
    main_prompt = f"""
You are an intelligent booking assistant. Handle the entire booking conversation naturally.

CURRENT DATE: {datetime.utcnow().strftime('%Y-%m-%d')}

AVAILABLE DATA:
{json.dumps(dataset_info, indent=2)}

CONVERSATION HISTORY:
{formatted_history}

CURRENT BOOKING DATA (if any):
{json.dumps(existing_booking_data, indent=2) if existing_booking_data else "No data collected yet"}

USER'S CURRENT MESSAGE:
{user_message}

YOUR TASK:
1. Analyze the conversation and current booking data
2. Extract any new information from the user's message
3. Validate that pickup_point and dropping_point are from the SAME district's dropping_points
4. Calculate fare from the dropping_point's price when dropping_point is selected
5. Determine the next action (ask for info, confirm, or complete booking)
6. Generate appropriate response
7. Ask for missing information in a natural way

BOOKING FIELDS NEEDED:
- district_from: District name (must be from available districts)
- district_to: District name (must be from available districts)
- pickup_point: Pickup location (must be from district_from's dropping_points)
- dropping_point: Dropping location (must be from district_to's dropping_points)
- bus_provider: Bus provider must be from available for both pickup and dropping district.
- name: Full name
- phone: Phone number
- date: Travel date (YYYY-MM-DD format)
- seats: Number of seats (integer)
- fare: Price per seat (auto-calculated from dropping_point)

IMPORTANT RULES:
- District names like "Dhaka", "Bogra" are NOT pickup/dropping points
- pickup_point and dropping_point must be actual location names from the district's list
- When dropping_point is selected, automatically set fare from its price
- Only show available bus providers for the selected district
- Ask for information in a natural, conversational way
- When user confirms (says yes, confirm, ok, etc.) and all data is complete, proceed to booking

RESPONSE FORMAT (JSON):
{{
    "action": "ask_info" | "confirm_booking" | "complete_booking",
    "updated_booking_data": {{
        "district_from": "value or null",
        "district_to": "value or null",
        "pickup_point": "value or null",
        "dropping_point": "value or null",
        "bus_provider": "value or null",
        "name": "value or null",
        "phone": "value or null",
        "date": "YYYY-MM-DD or null",
        "seats": number or null,
        "fare": number or null
    }},
    "response_to_user": "Your natural conversational response here"
}}

EXAMPLES OF GOOD RESPONSES:
- For missing district_from and district_to: "Which district would you like to travel to? We cover Dhaka, Chattogram, Khulna, Rajshahi, Sylhet, Barishal, Rangpur, Mymensingh, Comilla, and Bogra."
- For missing pickup point: "Great! In Chattogram, we have pickup points at Muradpur, Agrabad, and Kaptai. Which one would you prefer?"
- For confirmation: "Perfect! Let me confirm your booking: [details]. Shall I proceed with this booking?"

Return ONLY the JSON response, nothing else.
"""
    
    try:
        llm_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": main_prompt}],
            temperature=0.3
        )
        
        # Parse LLM response
        response_text = llm_response.choices[0].message.content.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        llm_data = json.loads(response_text)
        
        action = llm_data.get("action")
        updated_booking_data = llm_data.get("updated_booking_data", {})
        response_to_user = llm_data.get("response_to_user", "")
        
        # Handle based on action
        if action == "complete_booking":
            # Create booking record
            booking_id = str(uuid.uuid4())
            booking_record = {
                "booking_id": booking_id,
                "user_id": updated_booking_data.get("user_id"),
                "name": updated_booking_data.get("name"),
                "phone": updated_booking_data.get("phone"),
                "district_from": updated_booking_data.get("district_from"),
                "district_to": updated_booking_data.get("district_to"),
                "pickup_point": updated_booking_data.get("pickup_point"),
                "dropping_point": updated_booking_data.get("dropping_point"),
                "date": updated_booking_data.get("date"),
                "seats": updated_booking_data.get("seats"),
                "bus_provider": updated_booking_data.get("bus_provider"),
                "fare": updated_booking_data.get("fare"),
                "total_amount": updated_booking_data.get("fare", 0) * updated_booking_data.get("seats", 0),
                "pyment_status": "pending",
                "status": "confirmed",
                "booked_at": datetime.utcnow()
            }
            
            # Save to database
            db["bookings"].insert_one(booking_record)
            
            # Clear booking data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$unset": {"booking_data": ""}}
            )
            
            state.result = f"""
✅ Booking Confirmed!

🎫 Booking ID: {booking_id}
👤 Name: {booking_record['name']}
📞 Phone: {booking_record['phone']}
🚌 Bus Provider: {booking_record['bus_provider']}
📍 District From: {booking_record['district_from']}
📍  District To: {booking_record['district_to']}
🔵 Pickup Point: {booking_record['pickup_point']}
🔴 Dropping Point: {booking_record['dropping_point']}
📅 Date: {booking_record['date']}
💺 Seats: {booking_record['seats']}
💰 Fare per seat: ৳{booking_record['fare']}
💵 Total Amount: ৳{booking_record['total_amount']}
💵 payment Status: {booking_record['pyment_status']}

Your ticket has been successfully booked! 🎉
"""
        
        else:
            # Save updated booking data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$set": {"booking_data": updated_booking_data}}
            )
            
            state.result = response_to_user
        
        return state
    
    except Exception as e:
        state.result = f"Sorry, I encountered an error: {str(e)}"
        return state

def view_ticket(state: ChatState):
    """
    View user's booked tickets by phone number
    """
    thread_id = state.thread_id
    user_message = state.user_message
    
    # Fetch chat history
    chat_doc = chat_collection.find_one(
        {"thread_id": thread_id},
        {"chat": 1, "view_ticket_phone": 1}
    )
    
    if not chat_doc:
        state.result = "Sorry, I couldn't find your conversation history."
        return state
    
    chat_history = chat_doc.get("chat", [])
    stored_phone = chat_doc.get("view_ticket_phone")
    
    # Format chat history for LLM
    formatted_history = "\n".join([
        f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}"
        for msg in chat_history[-10:]
    ])
    
    # Extract phone number using LLM
    extraction_prompt = f"""
You are a ticket viewing assistant. Extract the phone number from the conversation.

CHAT HISTORY:
{formatted_history}

CURRENT USER MESSAGE:
{user_message}

STORED PHONE (if any):
{stored_phone}

Extract the phone number that the user wants to check tickets for.
Return ONLY the phone number, nothing else. If no phone number is found, return "NOT_FOUND".

Examples:
- "show my tickets" → extract from chat history or stored phone
- "my number is +8801712345678" → +8801712345678
- "01712345678" → 01712345678
- "check tickets for 01812345678" → 01812345678
"""
    
    try:
        extraction_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0
        )
        
        phone = extraction_response.choices[0].message.content.strip()
        
        if phone == "NOT_FOUND" or not phone:
            state.result = """
I need your phone number to retrieve your tickets.

Please provide the phone number you used when booking.
Example: 01712345678 or +8801712345678
"""
            return state
        
        # Store phone for future reference
        chat_collection.update_one(
            {"thread_id": thread_id},
            {"$set": {"view_ticket_phone": phone}}
        )
        
        # Search for bookings with this phone number
        bookings = list(db["bookings"].find(
            {"phone": {"$regex": phone.replace("+", "\\+"), "$options": "i"}},
            {"_id": 0}
        ).sort("booked_at", -1))
        
        if not bookings:
            state.result = f"""
No tickets found for phone number: {phone}

Please check if:
- The phone number is correct
- You have any confirmed bookings
"""
            return state
        
        # Format ticket information
        ticket_list = []
        for idx, booking in enumerate(bookings, 1):
            status_emoji = "✅" if booking.get("status") == "confirmed" else "❌"
            ticket_info = f"""
━━━━━━━━━━━━━━━━━━━━━━
🎫 Ticket #{idx}
{status_emoji} Status: {booking.get('status', 'unknown').upper()}
📋 Booking ID: {booking.get('booking_id')}
👤 Name: {booking.get('name')}
📞 Phone: {booking.get('phone')}
📍 From: {booking.get('pickup_point')}
📍 To: {booking.get('dropping_point')}
📅 Date: {booking.get('date')}
💺 Seats: {booking.get('seats')}
🕐 Booked: {booking.get('booked_at', 'N/A')}
"""
            ticket_list.append(ticket_info)
        
        tickets_display = "\n".join(ticket_list)
        state.result = f"""
📱 Tickets for {phone}:

{tickets_display}
━━━━━━━━━━━━━━━━━━━━━━

Total tickets: {len(bookings)}

To cancel a ticket, please provide the booking ID.
"""
        return state
    
    except Exception as e:
        state.result = f"Sorry, I encountered an error while retrieving your tickets: {str(e)}"
        return state


def cancel_ticket(state: ChatState):
    """
    Cancel a ticket using phone number and booking ID or date
    """
    thread_id = state.thread_id
    user_message = state.user_message.lower()
    
    # Fetch chat history
    chat_doc = chat_collection.find_one(
        {"thread_id": thread_id},
        {"chat": 1, "cancel_data": 1}
    )
    
    if not chat_doc:
        state.result = "Sorry, I couldn't find your conversation history."
        return state
    
    chat_history = chat_doc.get("chat", [])
    cancel_data = chat_doc.get("cancel_data", {})
    
    # Format chat history for LLM
    formatted_history = "\n".join([
        f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}"
        for msg in chat_history[-10:]
    ])
    
    # Check if user is confirming cancellation
    confirmation_keywords = ["yes", "confirm", "cancel it", "proceed", "ok", "sure", "definitely"]
    is_confirming = any(keyword in user_message for keyword in confirmation_keywords)
    
    # If awaiting confirmation and user confirms
    if cancel_data.get("awaiting_confirmation") and is_confirming:
        booking_id = cancel_data.get("booking_id")
        
        # Update booking status to cancelled
        result = db["bookings"].update_one(
            {"booking_id": booking_id},
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            # Clear cancel_data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$unset": {"cancel_data": ""}}
            )
            
            state.result = f"""
✅ Ticket Cancelled Successfully!

Booking ID: {booking_id}
Status: CANCELLED
Cancelled at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}

Your ticket has been cancelled. If you paid online, the refund will be processed within 5-7 business days.
"""
            return state
        else:
            state.result = "Failed to cancel the ticket. Please try again or contact support."
            return state
    
    # Extract cancellation information using LLM
    extraction_prompt = f"""
You are a ticket cancellation assistant. Extract the phone number and booking identifier from the conversation.

CHAT HISTORY:
{formatted_history}

CURRENT USER MESSAGE:
{user_message}

EXISTING CANCEL DATA (if any):
{cancel_data}

Extract the following information:
- phone: Phone number
- booking_id: Booking ID (if provided)
- date: Travel date (if provided as identifier, format: YYYY-MM-DD)

RULES:
1. Booking ID takes priority over date for identification
2. Only extract clearly stated information
3. Use existing data if not provided again
4. Today's date is {datetime.utcnow().strftime('%Y-%m-%d')}

Return ONLY a JSON object:
{{
    "phone": "value or null",
    "booking_id": "value or null",
    "date": "YYYY-MM-DD or null"
}}
"""
    
    try:
        import json
        extraction_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0
        )
        
        extracted_text = extraction_response.choices[0].message.content.strip()
        if "```json" in extracted_text:
            extracted_text = extracted_text.split("```json")[1].split("```")[0].strip()
        elif "```" in extracted_text:
            extracted_text = extracted_text.split("```")[1].split("```")[0].strip()
        
        extracted_data = json.loads(extracted_text)
        
        # Merge with existing data
        for key, value in extracted_data.items():
            if value is not None:
                cancel_data[key] = value
        
        # Check if we have enough information
        if not cancel_data.get("phone"):
            state.result = """
To cancel a ticket, I need your phone number.

Please provide:
📞 Your phone number (e.g., 01712345678)
"""
            return state
        
        if not cancel_data.get("booking_id") and not cancel_data.get("date"):
            # Show user's tickets to help them choose
            phone = cancel_data.get("phone")
            bookings = list(db["bookings"].find(
                {
                    "phone": {"$regex": phone.replace("+", "\\+"), "$options": "i"},
                    "status": "confirmed"
                },
                {"_id": 0}
            ).sort("booked_at", -1))
            
            if not bookings:
                state.result = f"""
No active tickets found for phone number: {phone}

Please check if:
- The phone number is correct
- You have any confirmed bookings that can be cancelled
"""
                return state
            
            # Show available tickets
            ticket_list = []
            for idx, booking in enumerate(bookings, 1):
                ticket_info = f"""
🎫 Option {idx}:
   Booking ID: {booking.get('booking_id')}
   Date: {booking.get('date')}
   Route: {booking.get('pickup_point')} → {booking.get('dropping_point')}
   Seats: {booking.get('seats')}
"""
                ticket_list.append(ticket_info)
            
            tickets_display = "\n".join(ticket_list)
            
            # Store phone for next interaction
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$set": {"cancel_data": cancel_data}}
            )
            
            state.result = f"""
📱 Active tickets for {phone}:

{tickets_display}

Please provide either:
- Booking ID (e.g., abc123-def456)
- Travel date (e.g., 2024-12-25)
"""
            return state
        
        # Find the booking
        query = {"phone": {"$regex": cancel_data["phone"].replace("+", "\\+"), "$options": "i"}}
        
        if cancel_data.get("booking_id"):
            query["booking_id"] = cancel_data["booking_id"]
        elif cancel_data.get("date"):
            query["date"] = cancel_data["date"]
        
        query["status"] = "confirmed"  # Only cancel confirmed tickets
        
        booking = db["bookings"].find_one(query, {"_id": 0})
        
        if not booking:
            state.result = """
❌ No matching ticket found.

Possible reasons:
- Booking ID or date is incorrect
- Ticket is already cancelled
- Phone number doesn't match

Please verify your information and try again.
"""
            # Clear cancel data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$unset": {"cancel_data": ""}}
            )
            return state
        
        # Ask for confirmation
        cancel_data["booking_id"] = booking.get("booking_id")
        cancel_data["awaiting_confirmation"] = True
        
        chat_collection.update_one(
            {"thread_id": thread_id},
            {"$set": {"cancel_data": cancel_data}}
        )
        
        state.result = f"""
⚠️ Confirm Ticket Cancellation

📋 Booking ID: {booking.get('booking_id')}
👤 Name: {booking.get('name')}
📞 Phone: {booking.get('phone')}
📍 Route: {booking.get('pickup_point')} → {booking.get('dropping_point')}
📅 Date: {booking.get('date')}
💺 Seats: {booking.get('seats')}

Are you sure you want to cancel this ticket?
Type 'yes' to confirm or 'no' to keep the booking.
"""
        return state
    
    except Exception as e:
        state.result = f"Sorry, I encountered an error while processing cancellation: {str(e)}"
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
