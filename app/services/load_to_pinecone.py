import os
import json
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)


# ---------- Create Pinecone index if missing ---------- #
def init_index():
    if INDEX_NAME not in pc.list_indexes().names():
        pc.create_index(
            name=INDEX_NAME,
            dimension=3072,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(INDEX_NAME)

def get_index():
    return init_index()

# ---------- Helper: embed text ---------- #
def embed_text(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return response.data[0].embedding


# ---------- Load all .txt files ---------- #
def load_files(folder="data"):
    docs = []
    for filename in os.listdir(folder):
        if filename.endswith(".txt"):
            path = os.path.join(folder, filename)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

            docs.append({
                "id": filename,
                "text": text
            })
    return docs


# ---------- Main function: upload only missing embeddings ---------- #
def upload_embeddings_if_missing():
    index = init_index()

    docs = load_files()
    all_ids = [doc["id"] for doc in docs]

    # Fetch which IDs already exist
    # (Pinecone only supports describe in batches)
    existing = set()

    # Batch check (safe for large sets)
    BATCH = 100
    for i in range(0, len(all_ids), BATCH):
        batch = all_ids[i:i+BATCH]
        res = index.fetch(batch)
        existing.update(res.vectors.keys())

    to_upload = [d for d in docs if d["id"] not in existing]

    if not to_upload:
        print("Embeddings already exist. No upload needed.")
        return

    print(f"{len(to_upload)} new files found. Uploading...")

    vectors = []
    for doc in to_upload:
        emb = embed_text(doc["text"])
        vectors.append({
            "id": doc["id"],
            "values": emb,
            "metadata": {
                "source": doc["id"],
                "text": doc["text"]
            }
        })

    index.upsert(vectors)
    print("Upload completed.")
