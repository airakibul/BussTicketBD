from pydantic import BaseModel
from typing import Optional, Any

class ChatInput(BaseModel):
    message: str
    user_id: str  # to associate chat with a user
    thread_id: Optional[str] = None  # optional, can create new thread
    
    
    
# =====================================================
# CHAT STATE
# =====================================================
class ChatState(BaseModel):
    user_message: str
    intent: Optional[str] = None
    result: Any = None
    thread_id: Optional[str] = None  # optional, can create new thread