from app.schemas.chat_schema import ChatState
from app.config import client
from app.services.load_to_pinecone import get_index

index = get_index()

def embed(text: str):
    res = client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return res.data[0].embedding

def provider_info(state: ChatState):
    query = state.user_message

    try:
        vector = embed(query)
        results = index.query(vector=vector, top_k=1, include_metadata=True)

        if not results["matches"]:
            state.result = "No relevant information found for this provider."
            return state

        text_blocks = [m["metadata"].get("text", "") for m in results["matches"]]
        context_str = "\n\n".join(text_blocks)

        prompt = f"""
Use the following context to answer the user query.

Context:
{context_str}

User Query:
{query}

Answer:
"""
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Answer based only on the provided context."},
                {"role": "user", "content": prompt}
            ]
        )

        state.result = completion.choices[0].message.content
        return state

    except Exception as e:
        state.result = f"Error: {str(e)}"
        return state
