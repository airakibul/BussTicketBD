import os
import json
from app.config import db



districts_collection = db["busses"]
providers_collection = db["busses"]


async def startup_event():
    try:
        with open("data.json", "r") as f:
            data = json.load(f)

        districts = data.get("districts", [])
        providers = data.get("bus_providers", [])

        # Insert Districts
        for d in districts:
            name = d.get("name")
            if not name:
                continue

            exists = districts_collection.find_one({"name": name})
            if not exists:
                districts_collection.insert_one(d)
                print(f"Inserted district: {name}")
            else:
                print(f"Skipped (duplicate) district: {name}")

        # Insert Bus Providers
        for p in providers:
            name = p.get("name")
            if not name:
                continue

            exists = providers_collection.find_one({"name": name})
            if not exists:
                providers_collection.insert_one(p)
                print(f"Inserted provider: {name}")
            else:
                print(f"Skipped (duplicate) provider: {name}")

        print("Startup data loaded successfully.")

    except Exception as e:
        print(f"Error loading data.json: {e}")
