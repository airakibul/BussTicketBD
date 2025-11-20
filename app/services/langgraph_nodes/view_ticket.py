from app.schemas.chat_schema import ChatState
from app.config import client, chat_collection, db




def view_ticket(state: ChatState):
    """
    View user's booked tickets by phone number
    """
    thread_id = state.thread_id
    user_message = state.user_message
    
    # Fetch chat history
    chat_doc = chat_collection.find_one(
        {"thread_id": thread_id},
        {"chat": 1, "view_ticket_phone": 1}
    )
    
    if not chat_doc:
        state.result = "Sorry, I couldn't find your conversation history."
        return state
    
    chat_history = chat_doc.get("chat", [])
    stored_phone = chat_doc.get("view_ticket_phone")
    
    # Format chat history for LLM
    formatted_history = "\n".join([
        f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}"
        for msg in chat_history[-10:]
    ])
    
    # Extract phone number using LLM
    extraction_prompt = f"""
You are a ticket viewing assistant. Extract the phone number from the conversation.

CHAT HISTORY:
{formatted_history}

CURRENT USER MESSAGE:
{user_message}

STORED PHONE (if any):
{stored_phone}

Extract the phone number that the user wants to check tickets for.
Return ONLY the phone number, nothing else. If no phone number is found, return "NOT_FOUND".

Examples:
- "show my tickets" → extract from chat history or stored phone
- "my number is +8801712345678" → +8801712345678
- "01712345678" → 01712345678
- "check tickets for 01812345678" → 01812345678
"""
    
    try:
        extraction_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0
        )
        
        phone = extraction_response.choices[0].message.content.strip()
        
        if phone == "NOT_FOUND" or not phone:
            state.result = """
I need your phone number to retrieve your tickets.

Please provide the phone number you used when booking.
Example: 01712345678 or +8801712345678
"""
            return state
        
        # Store phone for future reference
        chat_collection.update_one(
            {"thread_id": thread_id},
            {"$set": {"view_ticket_phone": phone}}
        )
        
        # Search for bookings with this phone number
        bookings = list(db["bookings"].find(
            {"phone": {"$regex": phone.replace("+", "\\+"), "$options": "i"}},
            {"_id": 0}
        ).sort("booked_at", -1))
        
        if not bookings:
            state.result = f"""
No tickets found for phone number: {phone}

Please check if:
- The phone number is correct
- You have any confirmed bookings
"""
            return state
        
        # Format ticket information
        ticket_list = []
        for idx, booking in enumerate(bookings, 1):
            status_emoji = "✅" if booking.get("status") == "confirmed" else "❌"
            ticket_info = f"""
🎫 Ticket #{idx}
{status_emoji} Status: {booking.get('status', 'unknown').upper()}
📋 Booking ID: {booking.get('booking_id')}
👤 Name: {booking.get('name')}
📞 Phone: {booking.get('phone')}
🚌 Bus Provider: {booking.get('bus_provider')}
📍 From: {booking.get('pickup_point')}
📍 To: {booking.get('dropping_point')}
📅 Date: {booking.get('date')}
💺 Seats: {booking.get('seats')}
💰 Fare per seat: ৳{booking.get('fare')}
💵 Total Amount: ৳{booking.get('total_amount')}
💵 payment Status: {booking.get('pyment_status')}
🕐 Booked: {booking.get('booked_at', 'N/A')}
"""
            ticket_list.append(ticket_info)
        
        tickets_display = "\n".join(ticket_list)
        state.result = f"""
📱 Tickets for {phone}:

{tickets_display}

Total tickets: {len(bookings)}

To cancel a ticket, please provide the booking ID.
"""
        return state
    
    except Exception as e:
        state.result = f"Sorry, I encountered an error while retrieving your tickets: {str(e)}"
        return state
