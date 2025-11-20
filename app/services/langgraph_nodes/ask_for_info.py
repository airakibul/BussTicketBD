import json
from typing import Any, Dict, List, Optional

from app.schemas.chat_schema import ChatState
from app.config import client, chat_collection, bus_collection


def _format_chat_history(chat: Optional[Dict[str, Any]]) -> str:
    if not chat:
        return "No prior conversation."
    history = chat.get("chat", []) or []
    if not history:
        return "No prior conversation."
    lines: List[str] = []
    for msg in history[-10:]:
        user_part = msg.get("user")
        bot_part = msg.get("bot")
        if user_part:
            lines.append(f"User: {user_part}")
        if bot_part:
            lines.append(f"Bot: {bot_part}")
    return "\n".join(lines) or "No prior conversation."


def _extract_route_fields(
    user_message: str,
    chat_history_text: str,
    district_names: List[str],
):
    prompt = f"""
You are given the user's latest message, recent chat history, and the list of districts we serve.
Determine the most likely departure (from_district) and destination (to_district) districts the user is asking about.
Only use district names from this list: {district_names}.

Return a JSON object with keys:
- from_district: district name or null
- to_district: district name or null
- missing_fields: array containing any field names you could not determine (use "from_district" and/or "to_district")

CHAT HISTORY:
{chat_history_text}

LATEST USER MESSAGE:
{user_message}
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content)


def _matching_providers(
    providers: List[Dict[str, Any]],
    from_district: str,
    to_district: str,
) -> List[str]:
    matches: List[str] = []
    for provider in providers:
        coverage = provider.get("coverage_districts", []) or []
        if (
            from_district in coverage
            and to_district in coverage
        ):
            matches.append(provider.get("name", "Unknown"))
    return matches


def _build_missing_message(missing_fields: List[str], district_names: List[str]) -> str:
    prompts: List[str] = []
    readable_names = ", ".join(district_names)
    if "from_district" in missing_fields:
        prompts.append(
            f"Which district are you departing from? We currently support {readable_names}."
        )
    if "to_district" in missing_fields:
        prompts.append(
            f"Where do you want to travel to? I can share details for {readable_names}."
        )
    if not prompts:
        prompts.append(
            "Could you clarify both your departure and destination districts so I can check the right buses?"
        )
    return " ".join(prompts)


def _compose_info_message(
    from_district: str,
    to_district: str,
    providers: List[str],
    dropping_points: List[Dict[str, Any]],
) -> str:
    lines = [f"Yes, buses operate from {from_district} to {to_district}."]
    if providers:
        lines.append(
            "Available operators covering both districts: "
            + ", ".join(providers)
            + "."
        )
    else:
        lines.append(
            "I couldn't find a provider in our data that serves both districts directly."
        )

    if dropping_points:
        fare_values = [dp.get("price") for dp in dropping_points if isinstance(dp.get("price"), (int, float))]
        points_text = ", ".join(
            f"{dp.get('name')} (৳{dp.get('price')})" if dp.get("price") is not None else dp.get("name")
            for dp in dropping_points if dp.get("name")
        )
        if points_text:
            lines.append(f"Common dropping points in {to_district}: {points_text}.")
        if fare_values:
            lines.append(
                f"Fares typically range from ৳{min(fare_values)} to ৳{max(fare_values)} per seat."
            )

    lines.append("Let me know if you need schedules or seat availability details.")
    return "\n".join(lines)


def _fallback_freeform_response(
    user_message: str,
    dataset: Dict[str, Any],
    chat_history_text: str,
):
    prompt = f"""
You are a bus route search assistant.

Use the conversation history and the structured data to answer the user's question with accurate, concise information.

CHAT HISTORY:
{chat_history_text}

USER MESSAGE:
{user_message}

DISTRICTS WITH DROPPING POINTS:
{dataset.get('districts')}

BUS PROVIDERS:
{dataset.get('bus_providers')}

Rules:
- Mention only bus providers that cover both the departure and destination districts.
- Reference the relevant dropping points and fares when possible.
- Keep the response short and natural. Do NOT respond in JSON.
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def ask_for_info(state: ChatState):
    dataset = bus_collection.find_one({}, {"districts": 1, "bus_providers": 1})
    if not dataset:
        state.result = "Sorry, I couldn't load the route information right now. Please try again later."
        return state

    districts = dataset.get("districts", []) or []
    bus_providers = dataset.get("bus_providers", []) or []
    district_names = [d.get("name") for d in districts if d.get("name")]

    chat = chat_collection.find_one({"thread_id": state.thread_id}, {"chat": {"$slice": -10}})
    chat_history_text = _format_chat_history(chat)

    try:
        route_data = _extract_route_fields(state.user_message, chat_history_text, district_names)
    except Exception:
        state.result = _fallback_freeform_response(state.user_message, dataset, chat_history_text)
        return state

    missing_fields = route_data.get("missing_fields") or []
    from_district = route_data.get("from_district")
    to_district = route_data.get("to_district")

    if missing_fields or not (from_district and to_district):
        state.result = _build_missing_message(missing_fields, district_names)
        return state

    dropping_points = next(
        (
            d.get("dropping_points", [])
            for d in districts
            if d.get("name", "").lower() == to_district.lower()
        ),
        [],
    )

    providers = _matching_providers(bus_providers, from_district, to_district)
    state.result = _compose_info_message(from_district, to_district, providers, dropping_points)
    return state
