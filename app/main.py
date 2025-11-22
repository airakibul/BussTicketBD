from fastapi import FastAPI
from app.api.routes.chat import chat_router
from app.services.buss_data_loader import startup_event

app = FastAPI()


@app.on_event("startup")
async def _startup_event():
    await startup_event()

app.include_router(chat_router)