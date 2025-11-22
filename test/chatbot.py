import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

app = FastAPI()

class ChatRequest(BaseModel):
    query: str

def embed(text: str):
    res = client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return res.data[0].embedding

def pinecone_search(query: str, top_k: int = 5):
    vector = embed(query)
    results = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True
    )
    return results["matches"]

def build_prompt(query: str, contexts):
    text_blocks = [match["metadata"].get("text", "") for match in contexts]
    context_str = "\n\n".join(text_blocks)

    return f"""
Use the following context to answer the user query.

Context:
{context_str}

User Query:
{query}

Answer:
"""

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        matches = pinecone_search(req.query)
        if not matches:
            return {"answer": "No relevant information found in Pinecone."}

        prompt = build_prompt(req.query, matches)

        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Answer based only on the provided context."},
                {"role": "user", "content": prompt}
            ]
        )

        answer = completion.choices[0].message.content
        return {"answer": answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
