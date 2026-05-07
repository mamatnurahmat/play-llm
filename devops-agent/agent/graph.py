from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import call_model, call_tools, should_continue

def create_graph():
    workflow = StateGraph(AgentState)

    # Tambahkan nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("action", call_tools)

    # Set entry point
    workflow.set_entry_point("agent")

    # Tambahkan conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "call_tools": "action",
            "end": END
        }
    )

    # Tambahkan edge biasa
    workflow.add_edge("action", "agent")

    return workflow.compile()

# Instance default
devops_agent = create_graph()
