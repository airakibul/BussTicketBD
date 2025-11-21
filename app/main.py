from fastapi import FastAPI
from app.api.routes.chat import chat_router

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    # Perform any startup initialization here
    
    pass

app.include_router(chat_router)