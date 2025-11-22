import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)

# -------- Create index if missing ----------#
if INDEX_NAME not in pc.list_indexes().names():
    pc.create_index(
        name=INDEX_NAME,
        dimension=3072,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )

index = pc.Index(INDEX_NAME)

# -------- Embed + upload ----------
def embed_text(text):
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return response.data[0].embedding

def load_files(folder="data"):
    all_docs = []
    for filename in os.listdir(folder):
        if filename.endswith(".txt"):
            path = os.path.join(folder, filename)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

            all_docs.append({
                "id": filename,
                "text": text
            })
    return all_docs

docs = load_files()

vectors = []
for doc in docs:
    emb = embed_text(doc["text"])
    vectors.append({
        "id": doc["id"],
        "values": emb,
        "metadata": {
            "source": doc["id"],
            "text": doc["text"]   # store full raw text here
        }
    })

index.upsert(vectors)
print("Upload completed.")
