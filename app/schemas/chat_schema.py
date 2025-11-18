from pydantic import BaseModel
from typing import Optional

class ChatInput(BaseModel):
    message: str
    user_id: str  # to associate chat with a user
    thread_id: Optional[str] = None  # optional, can create new thread