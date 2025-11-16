import os
import uuid
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv
from typing import Optional
from openai import OpenAI

load_dotenv()

# ============================
# ENV + DB SETUP
# ============================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = MongoClient(MONGO_URI)
db = client["BussTicketBD"]

busses_col = db["busses"]
bookings_col = db["bookings"]

ai = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="Bus Booking ChatBot API")


# ============================
# MODELS
# ============================
class ChatRequest(BaseModel):
    message: str
    phone: Optional[str] = None


# ============================
# Helper – Load provider file
# ============================
def load_provider_file(provider_name: str):
    file_path = f"providers/{provider_name}.txt"
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r") as f:
        return f.read()


# ============================
# Core Logic — Process Query
# ============================
def process_user_intent(user_message: str, phone: Optional[str]):
    bus_data = busses_col.find_one({})
    districts = bus_data["districts"]
    providers = bus_data["bus_providers"]

    msg = user_message.lower()

    # ---------------------------------------------------------
    # INTENT 1 — Search Bus (price, from → to)
    # ---------------------------------------------------------
    if "bus" in msg and ("from" in msg and "to" in msg):
        # naive extraction
        words = msg.split()
        if "from" in words and "to" in words:
            from_idx = words.index("from") + 1
            to_idx = words.index("to") + 1
            from_dist = words[from_idx].capitalize()
            to_dist = words[to_idx].capitalize()
        else:
            raise HTTPException(400, "Could not extract districts")

        # price extraction
        max_price = None
        for w in words:
            if w.isdigit():
                max_price = int(w)

        # find provider
        to_d = next((d for d in districts if d["name"] == to_dist), None)
        if not to_d:
            return {"reply": f"No data for district {to_dist}"}

        # filter price
        droppings = (
            [p for p in to_d["dropping_points"] if max_price is None or p["price"] <= max_price]
        )

        bus_list = [
            p["name"] for p in providers
            if from_dist in p["coverage_districts"] and to_dist in p["coverage_districts"]
        ]

        return {
            "reply": f"Buses from {from_dist} to {to_dist}: {bus_list}. Dropping points: {droppings}"
        }

    # ---------------------------------------------------------
    # INTENT 2 — Provider Info
    # ---------------------------------------------------------
    for p in providers:
        if p["name"].lower() in msg and ("contact" in msg or "details" in msg or "info" in msg):
            file_data = load_provider_file(p["name"])
            return {
                "reply": f"Provider: {p['name']}\nCoverage: {p['coverage_districts']}\n\nDetails:\n{file_data}"
            }

    # ---------------------------------------------------------
    # INTENT 3 — Booking
    # ---------------------------------------------------------
    if "book" in msg:
        # extremely simple extraction
        words = msg.split()

        # find districts
        from_dist = None
        to_dist = None
        for d in districts:
            if d["name"].lower() in msg:
                if "from" in msg and d["name"].lower() in msg[msg.index("from"):]:
                    from_dist = d["name"]
                elif "to" in msg and d["name"].lower() in msg[msg.index("to"):]:
                    to_dist = d["name"]

        # find provider
        provider = None
        for p in providers:
            if p["name"].lower() in msg:
                provider = p["name"]

        if not phone:
            return {"reply": "Phone number required to book. Add phone in request body."}

        booking_id = str(uuid.uuid4())
        record = {
            "booking_id": booking_id,
            "phone": phone,
            "from": from_dist,
            "to": to_dist,
            "provider": provider,
            "raw_message": user_message
        }
        bookings_col.insert_one(record)

        return {"reply": f"Booking confirmed. ID: {booking_id}"}

    # ---------------------------------------------------------
    # INTENT 4 — Cancel Booking
    # ---------------------------------------------------------
    if "cancel" in msg:
        words = msg.split()
        # naive find id
        for w in words:
            if len(w) > 25:  # uuid length
                booking_id = w
                result = bookings_col.delete_one({"booking_id": booking_id})
                if result.deleted_count == 0:
                    return {"reply": "No booking found with this ID"}
                else:
                    return {"reply": "Your booking has been cancelled"}

        return {"reply": "Booking ID missing. Please specify."}

    # ---------------------------------------------------------
    # INTENT 5 — View Bookings
    # ---------------------------------------------------------
    if "my booking" in msg or "my bookings" in msg or "show booking" in msg:
        if not phone:
            return {"reply": "Provide phone number to view bookings."}

        user_bookings = list(bookings_col.find({"phone": phone}, {"_id": 0}))
        return {"reply": user_bookings}

    # ---------------------------------------------------------
    # FALLBACK
    # ---------------------------------------------------------
    return {"reply": "I did not understand the request."}


# ============================
# Chat Endpoint
# ============================
@app.post("/chat")
def chat(req: ChatRequest):
    result = process_user_intent(req.message, req.phone)
    return result


# ============================
# Root
# ============================
@app.get("/")
def root():
    return {"message": "Chatbot Running", "endpoint": "/chat"}
