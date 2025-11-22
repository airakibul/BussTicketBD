import streamlit as st
import requests

API_URL = "http://localhost:8000/chat"  # your FastAPI endpoint
st.set_page_config(page_title="Chat", page_icon="💬")

# ======================================
# Session State
# ======================================
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

USER_ID = "himel"  # static for demo; replace with login if needed

# ======================================
# Chat History UI
# ======================================
st.title("Chat Interface")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["text"])

# ======================================
# User Input
# ======================================
user_input = st.chat_input("Type your message")

if user_input:
    # Show user message
    st.session_state.messages.append({"role": "user", "text": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    # Build payload exactly as required by your FastAPI
    payload = {
        "message": user_input,
        "user_id": USER_ID,
        "thread_id": st.session_state.thread_id
    }

    try:
        res = requests.post(API_URL, json=payload, timeout=30)
        res.raise_for_status()
        data = res.json()

        # Extract thread_id and response
        st.session_state.thread_id = data.get("thread_id")
        assistant_reply = data.get("response", "")

    except Exception as e:
        assistant_reply = f"Error contacting backend: {e}"

    # Show reply
    st.session_state.messages.append({"role": "assistant", "text": assistant_reply})
    with st.chat_message("assistant"):
        st.write(assistant_reply)
