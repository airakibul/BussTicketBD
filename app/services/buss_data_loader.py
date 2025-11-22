import json
from app.config import db

collection = db["busses"]

async def startup_event():
    try:
        with open("data.json", "r") as f:
            data = json.load(f)

        # Single object/document
        combined = {
            "_id": "startup_data",
            "districts": data.get("districts", []),
            "bus_providers": data.get("bus_providers", [])
        }

        # Insert or update
        collection.replace_one({"_id": "startup_data"}, combined, upsert=True)

        print("Data merged into one document.")

    except Exception as e:
        print(f"Error loading data.json: {e}")
