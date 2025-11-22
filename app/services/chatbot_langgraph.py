from langgraph.graph import StateGraph, END
from app.schemas.chat_schema import ChatState
from app.services.langgraph_nodes.detect_intent import detect_intent
from app.services.langgraph_nodes.ask_for_info import ask_for_info
from app.services.langgraph_nodes.provider_info import provider_info
from app.services.langgraph_nodes.book_ticket import book_ticket
from app.services.langgraph_nodes.view_ticket import view_ticket
from app.services.langgraph_nodes.cancel_ticket import cancel_ticket
from app.services.langgraph_nodes.general_chat import general_chat



graph = StateGraph(ChatState)
graph.add_node("general_chat", general_chat)
graph.add_node("detect_intent", detect_intent)
graph.add_node("ask_for_info", ask_for_info)
graph.add_node("provider_info", provider_info)
graph.add_node("book_ticket", book_ticket)
graph.add_node("view_ticket", view_ticket)
graph.add_node("cancel_ticket", cancel_ticket)
graph.set_entry_point("detect_intent")
graph.add_conditional_edges(
    "detect_intent",
    lambda state: state.intent,
    {
        "general_chat": "general_chat",
        "ask_for_info": "ask_for_info",
        "provider_info": "provider_info",
        "book_ticket": "book_ticket",
        "view_ticket": "view_ticket",
        "cancel_ticket": "cancel_ticket",
    }
)
for f in ["general_chat", "ask_for_info", "provider_info", "book_ticket", "view_ticket", "cancel_ticket"]:
    graph.add_edge(f, END)
flow = graph.compile()

