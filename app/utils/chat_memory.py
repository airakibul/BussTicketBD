from typing import Optional
from app.config import chat_collection
from datetime import datetime
import uuid


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
