
# BussTicketBD

A minimal chat-driven bus ticket assistant for Bangladesh. It uses FastAPI for the backend, Streamlit for a simple frontend demo, MongoDB for storage, and OpenAI for intent extraction and conversational responses. The project also uses langgraph to model conversation flows.

## Features
- LLM-driven intent detection and dialog nodes (search routes, book, view, cancel).
- MongoDB-backed data for districts, dropping points, and bookings.
- Streamlit demo UI for chat interaction.
- Docker Compose for easy local development with MongoDB.

## Prerequisites
- Python 3.11+
- Docker & Docker Compose (optional, recommended for easy setup)
- An OpenAI-compatible API key set in .env as OPENAI_API_KEY
- Pinecone key for using embedding features

## Quick setup (local)
1. Create and activate a virtual environment:
   - python -m venv .venv
   - source .venv/bin/activate
2. Install dependencies:
   - pip install --upgrade pip
   - pip install -r requirements.txt
3. Copy the example environment file and set secrets:
   - cp .env .env.local && edit .env.local (or edit .env directly)
   - Required: OPENAI_API_KEY, MONGO_URI (default in docker: mongodb://mongo:27017)
4. Ensure data.json exists at project root (used by startup loader).

## Run locally (without Docker)
1. Start MongoDB (if you don't use docker).
2. Start the app (FastAPI + Streamlit demo):
   - ./start.sh
   - Or run services separately:
     - uvicorn app.main:app --host 0.0.0.0 --port 8000
     - streamlit run frontend.py --server.port 8501

API: FastAPI runs on http://localhost:8000
Frontend: Streamlit chat demo runs on http://localhost:8501

## Run with Docker Compose (recommended)
1. Build and start services:
   - docker compose up --build
2. The stack will expose:
   - FastAPI: http://localhost:8000
   - Streamlit: http://localhost:8501
   - MongoDB: mongodb://localhost:27017

## Project Structure

```text
├── app
│   ├── api
│   │    └── routes
│   │          └── chat.py 
│   ├── schemas
│   │      └── chat_schena.py 
│   ├── services
│   │       ├── langgraph_nodes
│   │       │           ├── detect_intent.py
│   │       │           ├── general_chat.py
│   │       │           ├── ask_for_info.py
│   │       │           ├── book_ticket.py
│   │       │           ├── provider_info.py
│   │       │           ├── view_ticket.py
│   │       │           └── cancel_ticket.py
│   │       ├── chatbot_langgraph.py
│   │       ├── buss_data_loader.py
│   │       └── load_to_pinecone.py
│   ├── utils
│   │     └── chat_memory.py
│   ├── config.py
│   └── main.py
├── data
├── test
├── data.json
├── frontend.py
└── requirements.txt
```
## Langgraph

![Langgraph](https://github.com/airakibul/BussTicketBD/tree/main/images/langgraph.jpg)

## Notes
- The project expects a single aggregated document in the `busses` collection (created by the startup loader).
- Keep your OPENAI_API_KEY private; do not commit .env to version control.
- For production deployment, secure secrets and consider using a managed DB and API gateway.

## Troubleshooting
- If the frontend can't reach the backend, ensure FastAPI is running and the API_URL in frontend.py points to the correct host/port.
- Check logs for the `app` container or run uvicorn in the terminal to see startup errors.

## License
MIT-style (adjust as needed)