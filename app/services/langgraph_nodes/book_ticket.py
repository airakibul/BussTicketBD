from app.schemas.chat_schema import ChatState
from app.config import client, chat_collection, db, bus_collection
from datetime import datetime
import uuid




def book_ticket(state: ChatState):
    """
    LLM-driven booking process - minimal if/else, maximum LLM intelligence
    """
    import json
    
    thread_id = state.thread_id
    user_message = state.user_message
    
    # Fetch dataset from MongoDB
    dataset = bus_collection.find_one({}, {"districts": 1, "bus_providers": 1})
    if not dataset:
        state.result = "Sorry, the booking system is currently unavailable."
        return state
    
    districts = dataset.get("districts", [])
    bus_providers = dataset.get("bus_providers", [])
    
    # Fetch chat history
    chat_doc = chat_collection.find_one(
        {"thread_id": thread_id},
        {"chat": 1, "booking_data": 1}
    )
    
    if not chat_doc:
        state.result = "Sorry, I couldn't find your conversation history."
        return state
    
    chat_history = chat_doc.get("chat", [])
    existing_booking_data = chat_doc.get("booking_data", {})
    
    # Format chat history
    formatted_history = "\n".join([
        f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}"
        for msg in chat_history[-15:]
    ])
    
    # Format dataset for LLM
    dataset_info = {
        "districts": districts,
        "bus_providers": bus_providers
    }
    
    # Single LLM call to handle everything
    main_prompt = f"""
You are an intelligent booking assistant. Handle the entire booking conversation naturally.

CURRENT DATE: {datetime.utcnow().strftime('%Y-%m-%d')}

AVAILABLE DATA:
{json.dumps(dataset_info, indent=2)}

CONVERSATION HISTORY:
{formatted_history}

CURRENT BOOKING DATA (if any):
{json.dumps(existing_booking_data, indent=2) if existing_booking_data else "No data collected yet"}

USER'S CURRENT MESSAGE:
{user_message}

YOUR TASK:
1. Analyze the conversation and current booking data
2. Extract any new information from the user's message
3. Validate that pickup_point and dropping_point are from the SAME district's dropping_points
4. Calculate fare from the dropping_point's price when dropping_point is selected
5. Determine the next action (ask for info, confirm, or complete booking)
6. Generate appropriate response
7. Ask for missing information in a natural way

BOOKING FIELDS NEEDED:
- district_from: District name (must be from available districts)
- district_to: District name (must be from available districts)
- pickup_point: Pickup location (must be from district_from's dropping_points)
- dropping_point: Dropping location (must be from district_to's dropping_points)
- bus_provider: Bus provider must be from available for both pickup and dropping district.
- name: Full name
- phone: Phone number
- date: Travel date (YYYY-MM-DD format)
- seats: Number of seats (integer)
- fare: Price per seat (auto-calculated from dropping_point)

IMPORTANT RULES:
- District names like "Dhaka", "Bogra" are NOT pickup/dropping points
- For pickup points don't show the price
- Always show price for dropping point
- pickup_point and dropping_point must be actual location names from the district's list
- When dropping_point is selected, automatically set fare from its price
- Only show available bus providers for the selected district
- Ask for information in a natural, conversational way
- When user confirms (says yes, confirm, ok, etc.) and all data is complete, proceed to booking

RESPONSE FORMAT (JSON):
{{
    "action": "ask_info" | "confirm_booking" | "complete_booking",
    "updated_booking_data": {{
        "district_from": "value or null",
        "district_to": "value or null",
        "pickup_point": "value or null",
        "dropping_point": "value or null",
        "bus_provider": "value or null",
        "name": "value or null",
        "phone": "value or null",
        "date": "YYYY-MM-DD or null",
        "seats": number or null,
        "fare": number or null
    }},
    "response_to_user": "Your natural conversational response here"
}}

EXAMPLES OF GOOD RESPONSES:
- For missing district_from and district_to: "Which district would you like to travel to? We cover Dhaka, Chattogram, Khulna, Rajshahi, Sylhet, Barishal, Rangpur, Mymensingh, Comilla, and Bogra."
- For missing pickup point: "Great! In Chattogram, we have pickup points at Muradpur, Agrabad, and Kaptai. Which one would you prefer?"
- For confirmation: "Perfect! Let me confirm your booking: [details]. Shall I proceed with this booking?"

Return ONLY the JSON response, nothing else.
"""
    
    try:
        llm_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": main_prompt}],
            temperature=0.3
        )
        
        # Parse LLM response
        response_text = llm_response.choices[0].message.content.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        llm_data = json.loads(response_text)
        
        action = llm_data.get("action")
        updated_booking_data = llm_data.get("updated_booking_data", {})
        response_to_user = llm_data.get("response_to_user", "")
        
        # Handle based on action
        if action == "complete_booking":
            # Create booking record
            booking_id = str(uuid.uuid4())
            booking_record = {
                "booking_id": booking_id,
                "user_id": updated_booking_data.get("user_id"),
                "name": updated_booking_data.get("name"),
                "phone": updated_booking_data.get("phone"),
                "district_from": updated_booking_data.get("district_from"),
                "district_to": updated_booking_data.get("district_to"),
                "pickup_point": updated_booking_data.get("pickup_point"),
                "dropping_point": updated_booking_data.get("dropping_point"),
                "date": updated_booking_data.get("date"),
                "seats": updated_booking_data.get("seats"),
                "bus_provider": updated_booking_data.get("bus_provider"),
                "fare": updated_booking_data.get("fare"),
                "total_amount": updated_booking_data.get("fare", 0) * updated_booking_data.get("seats", 0),
                "pyment_status": "pending",
                "status": "confirmed",
                "booked_at": datetime.utcnow()
            }
            
            # Save to database
            db["bookings"].insert_one(booking_record)
            
            # Clear booking data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$unset": {"booking_data": ""}}
            )
            
            state.result = f"""
✅ Booking Confirmed!

🎫 Booking ID: {booking_id}
👤 Name: {booking_record['name']}
📞 Phone: {booking_record['phone']}
🚌 Bus Provider: {booking_record['bus_provider']}
📍 District From: {booking_record['district_from']}
📍  District To: {booking_record['district_to']}
🔵 Pickup Point: {booking_record['pickup_point']}
🔴 Dropping Point: {booking_record['dropping_point']}
📅 Date: {booking_record['date']}
💺 Seats: {booking_record['seats']}
💰 Fare per seat: ৳{booking_record['fare']}
💵 Total Amount: ৳{booking_record['total_amount']}
💵 payment Status: {booking_record['pyment_status']}

Your ticket has been successfully booked! 🎉
"""
        
        else:
            # Save updated booking data
            chat_collection.update_one(
                {"thread_id": thread_id},
                {"$set": {"booking_data": updated_booking_data}}
            )
            
            state.result = response_to_user
        
        return state
    
    except Exception as e:
        state.result = f"Sorry, I encountered an error: {str(e)}"
        return state
