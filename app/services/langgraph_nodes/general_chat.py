from app.schemas.chat_schema import ChatState
from app.config import client

def general_chat(state: ChatState):
    """Handles general conversation, greetings, and thank you messages"""
    
    prompt = f"""
You are a friendly bus ticket booking assistant.

User said: {state.user_message}

Respond naturally and warmly. If they:
- Greet you → greet back and briefly mention you can help with bus bookings
- Thank you → acknowledge politely
- Ask what you do → explain you help with bus ticket booking, viewing, and cancellation
- Off-topic → politely redirect to bus booking services

Keep it brief and friendly.
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    
    state.result = resp.choices[0].message.content.strip()
    return state