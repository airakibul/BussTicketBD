from app.schemas.chat_schema import ChatState
from app.config import client, chat_collection


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
- general_chat       → greetings (hi, hello), gratitude (thank you), casual chat, off-topic questions
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