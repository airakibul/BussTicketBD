import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any
from openai import OpenAI
from pymongo import MongoClient
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from pinecone import Pinecone
# =====================================================
# ENV + CLIENTS
# =====================================================
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = mongo["BussTicketBD"]
collection = db["busses"]
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX")
app = FastAPI()

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

app = FastAPI()

class ChatRequest(BaseModel):
    query: str

def embed(text: str):
    res = client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return res.data[0].embedding
# =====================================================
# GRAPH STATE
# =====================================================
class ChatState(BaseModel):
    user_message: str
    intent: str = None
    result: Any = None


# =====================================================
# INTENT DETECTOR
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
# FUNCTIONS USING MONGODB
# =====================================================

# 1. Search for buses between districts
def search_buses(state: ChatState):
    msg = state.user_message

    dataset = collection.find_one({}, {"districts": 1, "bus_providers": 1})

    prompt = f"""
    You are a bus route search assistant.

    User message:
    {msg}

    Data:
    Districts with dropping points:
    {dataset["districts"]}

    Bus Providers:
    {dataset["bus_providers"]}

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


# 2. Get bus provider information
def provider_info(state: ChatState):
    query = state.user_message

    try:
        # Embed the query
        vector = embed(query)

        # Search Pinecone index
        results = index.query(vector=vector, top_k=5, include_metadata=True)

        if not results["matches"]:
            state.result = "No relevant information found for this provider."
            return state

        # Build context for LLM
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

        # Call OpenAI ChatCompletion
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



# 3. Book ticket (placeholder)
def book_ticket(state: ChatState):
    # A real system would create a booking entry
    state.result = "Ticket booked (placeholder)."
    return state


# 4. View user ticket (placeholder)
def view_ticket(state: ChatState):
    state.result = "User ticket info (placeholder)."
    return state


# 5. Cancel ticket (placeholder)
def cancel_ticket(state: ChatState):
    state.result = "Ticket cancelled (placeholder)."
    return state


# =====================================================
# BUILD LANGGRAPH
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

for f in ["search_buses","provider_info","book_ticket","view_ticket","cancel_ticket"]:
    graph.add_edge(f, END)

flow = graph.compile()


# =====================================================
# FASTAPI ENDPOINT
# =====================================================
class ChatInput(BaseModel):
    message: str


@app.post("/chat")
async def chat_endpoint(data: ChatInput):
    state = {"user_message": data.message}
    out = flow.invoke(state)
    return out["result"]

