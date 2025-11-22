from fastapi import FastAPI
from app.api.routes.chat import chat_router
from app.services.buss_data_loader import startup_event
from app.services.load_to_pinecone import upload_embeddings_if_missing

app = FastAPI()


@app.on_event("startup")
async def _startup_event():
    await startup_event()
    upload_embeddings_if_missing()

app.include_router(chat_router)