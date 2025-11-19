from app.schemas.chat_schema import ChatState
from app.config import client, chat_collection, bus_collection



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
