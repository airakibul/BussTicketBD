
# BussTicketBD

A minimal chat-driven bus ticket assistant for Bangladesh.
It uses **FastAPI** for the backend, **Streamlit** for a lightweight frontend demo, **MongoDB** for operational data storage, **Pinecone** for **vector search** and **retrieval-augmented** responses, and **OpenAI** for intent extraction and conversational generation.
The project also uses LangGraph to model multi-step conversation flows and manage state.

## Features
- LLM-driven intent detection and dialog nodes.
   - **search routes**
   - **provider information**
   - **booking ticktets**
   - **view tickets**
   - **cancel tickets**
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
```bash
python -m venv .venv
source .venv/bin/activate
```
2. Install dependencies:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
3. Copy the example environment file and set secrets:
```bash
OPENAI_API_KEY=<your openai api key>
PINECONE_API_KEY=<your pinecone api key>
PINECONE_INDEX=<pinecone index>
MONGO_URI=<mongodb://mongo:27017>
```

## Run locally (without Docker)
1. Start MongoDB (if you don't use docker).
2. Start the app (FastAPI + Streamlit demo):
```bash
uvicorn app.main:app --reload
streamlit run frontend.py
```
API: FastAPI runs on http://localhost:8000 

Frontend: Streamlit chat runs on http://localhost:8501

## Run with Docker Compose (recommended)
1. Build and start services:
```bash
docker compose up --build
```
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
│   │      └── chat_schema.py 
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

![Langgraph](https://github.com/airakibul/BussTicketBD/blob/main/images/langgraph.png)

## Notes
- The project expects a single aggregated document in the `busses` collection and `buss provider information` in the vector database. (created by the startup loader).
- For production deployment, secure secrets and consider using a managed DB and API gateway.

## Troubleshooting
- If the frontend can't reach the backend, ensure FastAPI is running and the API_URL in frontend.py points to the correct host/port.
- Check logs for the `app` container or run uvicorn in the terminal to see startup errors.

## License
This project is licensed under the MIT License – see the [LICENSE](./LICENSE) file for details.

## Screenshot

![Screenshot](https://github.com/airakibul/BussTicketBD/blob/main/images/screenshot.png)
