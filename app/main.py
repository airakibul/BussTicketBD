from fastapi import FastAPI
from app.api.routes.chat import chat_router

app = FastAPI()

app.include_router(chat_router)