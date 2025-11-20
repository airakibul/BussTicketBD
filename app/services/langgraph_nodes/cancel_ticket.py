from app.schemas.chat_schema import ChatState
from app.config import client, chat_collection, db
from datetime import datetime




def cancel_ticket(state: ChatState):
    """
    Cancel a ticket using phone number and booking ID or date
    """
    thread_id = state.thread_id
    user_message = state.user_message.lower()
    
    # Fetch chat history
    chat_doc = chat_collection.find_one(
        {"thread_id": thread_id},
        {"chat": 1, "cancel_data": 1}
    )
    
    if not chat_doc:
        state.result = "Sorry, I couldn't find your conversation history."
        return state
    
    chat_history = chat_doc.get("chat", [])
    cancel_data = chat_doc.get("cancel_data", {})
    
    # Format chat history for LLM
    formatted_history = "\n".join([
        f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}"
        for msg in chat_history[-10:]
    ])
    
    # Check if user is confirming cancellation
    confirmation_keywords = ["yes", "confirm", "cancel it", "proceed", "ok", "sure", "definitely"]
    is_confirming = any(keyword in user_message for keyword in confirmation_keywords)
    
    # If awaiting confirmation and user confirms
    if cancel_data.get("awaiting_confirmation") and is_confirming:
        booking_id = cancel_data.get("booking_id")
        
        # Update booking status to cancelled
        result = db["bookings"].update_one(
            {"booking_id": booking_id},
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            # Clear cancel_data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$unset": {"cancel_data": ""}}
            )
            
            state.result = f"""
✅ Ticket Cancelled Successfully!

Booking ID: {booking_id}
Status: CANCELLED
Cancelled at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}

Your ticket has been cancelled. If you paid online, the refund will be processed within 5-7 business days.
"""
            return state
        else:
            state.result = "Failed to cancel the ticket. Please try again or contact support."
            return state
    
    # Extract cancellation information using LLM
    extraction_prompt = f"""
You are a ticket cancellation assistant. Extract the phone number and booking identifier from the conversation.

CHAT HISTORY:
{formatted_history}

CURRENT USER MESSAGE:
{user_message}

EXISTING CANCEL DATA (if any):
{cancel_data}

Extract the following information:
- phone: Phone number
- booking_id: Booking ID (if provided)
- date: Travel date (if provided as identifier, format: YYYY-MM-DD)

RULES:
1. Booking ID takes priority over date for identification
2. Only extract clearly stated information
3. Use existing data if not provided again
4. Today's date is {datetime.utcnow().strftime('%Y-%m-%d')}

Return ONLY a JSON object:
{{
    "phone": "value or null",
    "booking_id": "value or null",
    "date": "YYYY-MM-DD or null"
}}
"""
    
    try:
        import json
        extraction_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0
        )
        
        extracted_text = extraction_response.choices[0].message.content.strip()
        if "```json" in extracted_text:
            extracted_text = extracted_text.split("```json")[1].split("```")[0].strip()
        elif "```" in extracted_text:
            extracted_text = extracted_text.split("```")[1].split("```")[0].strip()
        
        extracted_data = json.loads(extracted_text)
        
        # Merge with existing data
        for key, value in extracted_data.items():
            if value is not None:
                cancel_data[key] = value
        
        # Check if we have enough information
        if not cancel_data.get("phone"):
            state.result = """
To cancel a ticket, I need your phone number.

Please provide:
📞 Your phone number (e.g., 01712345678)
"""
            return state
        
        if not cancel_data.get("booking_id") and not cancel_data.get("date"):
            # Show user's tickets to help them choose
            phone = cancel_data.get("phone")
            bookings = list(db["bookings"].find(
                {
                    "phone": {"$regex": phone.replace("+", "\\+"), "$options": "i"},
                    "status": "confirmed"
                },
                {"_id": 0}
            ).sort("booked_at", -1))
            
            if not bookings:
                state.result = f"""
No active tickets found for phone number: {phone}

Please check if:
- The phone number is correct
- You have any confirmed bookings that can be cancelled
"""
                return state
            
            # Show available tickets
            ticket_list = []
            for idx, booking in enumerate(bookings, 1):
                ticket_info = f"""
🎫 Option {idx}:
   Booking ID: {booking.get('booking_id')}
   Date: {booking.get('date')}
   Route: {booking.get('pickup_point')} → {booking.get('dropping_point')}
   Seats: {booking.get('seats')}
"""
                ticket_list.append(ticket_info)
            
            tickets_display = "\n".join(ticket_list)
            
            # Store phone for next interaction
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$set": {"cancel_data": cancel_data}}
            )
            
            state.result = f"""
📱 Active tickets for {phone}:

{tickets_display}

Please provide either:
- Booking ID (e.g., abc123-def456)
- Travel date (e.g., 2024-12-25)
"""
            return state
        
        # Find the booking
        query = {"phone": {"$regex": cancel_data["phone"].replace("+", "\\+"), "$options": "i"}}
        
        if cancel_data.get("booking_id"):
            query["booking_id"] = cancel_data["booking_id"]
        elif cancel_data.get("date"):
            query["date"] = cancel_data["date"]
        
        query["status"] = "confirmed"  # Only cancel confirmed tickets
        
        booking = db["bookings"].find_one(query, {"_id": 0})
        
        if not booking:
            state.result = """
❌ No matching ticket found.

Possible reasons:
- Booking ID or date is incorrect
- Ticket is already cancelled
- Phone number doesn't match

Please verify your information and try again.
"""
            # Clear cancel data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$unset": {"cancel_data": ""}}
            )
            return state
        
        # Ask for confirmation
        cancel_data["booking_id"] = booking.get("booking_id")
        cancel_data["awaiting_confirmation"] = True
        
        chat_collection.update_one(
            {"thread_id": thread_id},
            {"$set": {"cancel_data": cancel_data}}
        )
        
        state.result = f"""
⚠️ Confirm Ticket Cancellation

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

Are you sure you want to cancel this ticket?
Type 'yes' to confirm or 'no' to keep the booking.
"""
        return state
    
    except Exception as e:
        state.result = f"Sorry, I encountered an error while processing cancellation: {str(e)}"
        return state