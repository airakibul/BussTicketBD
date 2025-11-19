import json
from datetime import datetime
import uuid
from typing import Optional
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from openai import OpenAI
from crud import ChatState
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = mongo["BussTicketBD"]
chat_collection = db["chat_memory"]



booking_graph = StateGraph(ChatState)

class BookingState(BaseModel):
    thread_id: str
    user_message: str
    name: Optional[str] = None
    phone: Optional[str] = None
    pickup: Optional[str] = None
    drop: Optional[str] = None
    date: Optional[str] = None
    seat: Optional[str] = None
    confirmed: bool = False
    result: Optional[str] = None






def extract_fields(state: BookingState):
    chat = chat_collection.find_one(
        {"thread_id": state.thread_id},
        {"chat": {"$slice": -10}}
    )

    prompt = f"""
Extract the following fields from chat history + latest user message.
If missing return null.

Fields:
- name
- phone
- pickup
- drop
- date
- seat

CHAT HISTORY:
{chat}

LATEST MESSAGE:
{state.user_message}

Return ONLY a JSON object with keys:
name, phone, pickup, drop, date, seat
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},   # FORCE JSON
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    data = json.loads(resp.choices[0].message.content)

    for f in ["name", "phone", "pickup", "drop", "date", "seat"]:
        if data.get(f):
            setattr(state, f, data[f])

    return state



def check_missing(state: BookingState):
    missing = [f for f in ["name","phone","pickup","drop","date","seat"]
               if getattr(state, f) is None]

    if missing:
        state.result = f"I need the following to continue: {', '.join(missing)}."
        return "request_missing"

    return "ask_confirmation"


def request_missing(state: BookingState):
    return state


def ask_confirmation(state: BookingState):
    summary = f"""
Here is your booking information:

Name: {state.name}
Phone: {state.phone}
Pickup: {state.pickup}
Drop: {state.drop}
Date: {state.date}
Seat: {state.seat}

Please confirm: yes / ok / confirm
"""
    state.result = summary
    return state


def finalize_booking(state: BookingState):
    if any(x in state.user_message.lower() for x in ["yes","ok","confirm","sure"]):
        db["tickets"].insert_one({
            "thread_id": state.thread_id,
            "name": state.name,
            "phone": state.phone,
            "pickup": state.pickup,
            "drop": state.drop,
            "date": state.date,
            "seat": state.seat,
            "created_at": datetime.utcnow()
        })
        state.result = "Your ticket is confirmed."
        return state

    state.result = "Please confirm yes / ok / confirm."
    return state







booking_graph = StateGraph(BookingState)

booking_graph.add_node("extract_fields", extract_fields)
booking_graph.add_node("request_missing", request_missing)
booking_graph.add_node("ask_confirmation", ask_confirmation)
booking_graph.add_node("finalize_booking", finalize_booking)

booking_graph.set_entry_point("extract_fields")

booking_graph.add_conditional_edges(
    "extract_fields",
    check_missing,
    {
        "request_missing": "request_missing",
        "ask_confirmation": "ask_confirmation",
    }
)

booking_graph.add_edge("request_missing", "extract_fields")
booking_graph.add_edge("ask_confirmation", "finalize_booking")
booking_graph.add_edge("finalize_booking", END)

booking_flow = booking_graph.compile()
