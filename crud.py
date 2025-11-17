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

# =====================================================
# INTENT DETECTION
# =====================================================
def detect_intent(state: ChatState):
    prompt = f"""
    You MUST classify the message into EXACTLY one of these:
    - search_buses
    - provider_info
    - book_ticket
    - view_ticket
    - cancel_ticket

    Message: {state.user_message}

    Respond ONLY with the intent.
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
def search_buses(state: ChatState):
    msg = state.user_message
    dataset = bus_collection.find_one({}, {"districts": 1, "bus_providers": 1})

    prompt = f"""
    You are a bus route search assistant.

    User message:
    {msg}

    Data:
    Districts with dropping points:
    {dataset['districts']}

    Bus Providers:
    {dataset['bus_providers']}

    Task:
    - Understand what route the user is asking about.
    - Check which bus providers cover BOTH the from and to districts.
    - If no providers match, say that no buses are available.
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
        results = index.query(vector=vector, top_k=5, include_metadata=True)

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
    state.result = "Ticket booked (placeholder)."
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
graph.add_node("search_buses", search_buses)
graph.add_node("provider_info", provider_info)
graph.add_node("book_ticket", book_ticket)
graph.add_node("view_ticket", view_ticket)
graph.add_node("cancel_ticket", cancel_ticket)
graph.set_entry_point("detect_intent")
graph.add_conditional_edges(
    "detect_intent",
    lambda state: state.intent,
    {
        "search_buses": "search_buses",
        "provider_info": "provider_info",
        "book_ticket": "book_ticket",
        "view_ticket": "view_ticket",
        "cancel_ticket": "cancel_ticket",
    }
)
for f in ["search_buses", "provider_info", "book_ticket", "view_ticket", "cancel_ticket"]:
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

    state = {"user_message": data.message}
    out = flow.invoke(state)

    # Save chat to MongoDB
    store_message(thread_id, data.message, out["result"])

    return {"thread_id": thread_id, "response": out["result"]}
