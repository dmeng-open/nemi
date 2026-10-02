from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.state import PlanningState


def compile_planning_graph(nodes: dict, checkpointer: MemorySaver | None = None):
    graph = StateGraph(PlanningState)
    for name, node in nodes.items():
        graph.add_node(name, node)

    graph.add_edge(START, "parse_request")
    graph.add_conditional_edges(
        "parse_request",
        lambda state: "stop" if state.get("status") == "awaiting_clarification" else "continue",
        {"stop": END, "continue": "load_user_preferences"},
    )
    graph.add_edge("load_user_preferences", "get_calendar_availability")
    graph.add_edge("get_calendar_availability", "determine_plan_type")
    graph.add_conditional_edges(
        "determine_plan_type",
        lambda state: state.get("plan_type") or "event",
        {"event": "search_events", "restaurant": "search_restaurants"},
    )
    def _after_search(state: PlanningState) -> str:
        if state.get("status") == "awaiting_location":
            return "stop"
        return "continue"

    graph.add_conditional_edges(
        "search_events",
        _after_search,
        {"stop": END, "continue": "normalize_candidates"},
    )
    graph.add_conditional_edges(
        "search_restaurants",
        _after_search,
        {"stop": END, "continue": "normalize_candidates"},
    )
    graph.add_edge("normalize_candidates", "rank_candidates")
    graph.add_edge("rank_candidates", "verify_candidates")
    graph.add_edge("verify_candidates", "generate_recommendations")
    graph.add_conditional_edges(
        "generate_recommendations",
        lambda state: "stop" if state.get("status") in {"no_matches", "failed"} else "wait",
        {"stop": END, "wait": "wait_for_user_selection"},
    )
    graph.add_edge("wait_for_user_selection", "wait_for_user_approval")
    graph.add_conditional_edges(
        "wait_for_user_approval",
        lambda state: "schedule" if state.get("approved") else "stop",
        {"schedule": "create_calendar_plan", "stop": END},
    )
    graph.add_edge("create_calendar_plan", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())
