from fastapi import APIRouter
from app.schemas.chat_schema import ChatInput
from app.services.chatbot_langgraph import flow
from app.utils.chat_memory import create_or_get_thread, store_message

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(data: ChatInput):
    # Ensure thread exists
    thread_id = create_or_get_thread(data.user_id, data.thread_id)
    state = {"user_message": data.message, "thread_id": thread_id}
    out = flow.invoke(state)

    # Save chat to MongoDB
    store_message(thread_id, data.message, out["result"])

    return {"thread_id": thread_id, "response": out["result"]}

chat_router = router