"""LangGraph StateGraph definition — the main review pipeline."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from pr_review_agent.graph.conditions import after_context_confirmation
from pr_review_agent.graph.nodes import (
    analyze_pr_node,
    compute_recommendation_node,
    confirm_context_node,
    exit_with_instructions_node,
    fetch_pr_data,
    fetch_specific_page_node,
    format_output_node,
    generate_llm_brief_node,
    score_relevance_node,
    search_notion_node,
    summarize_pr_node,
)
from pr_review_agent.graph.state import AgentState


def build_workflow() -> StateGraph:
    """Build and compile the review workflow graph."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("fetch_pr_data", fetch_pr_data)
    graph.add_node("summarize_pr", summarize_pr_node)
    graph.add_node("search_notion", search_notion_node)
    graph.add_node("score_relevance", score_relevance_node)
    graph.add_node("confirm_context", confirm_context_node)
    graph.add_node("fetch_specific_page", fetch_specific_page_node)
    graph.add_node("exit_with_instructions", exit_with_instructions_node)
    graph.add_node("analyze_pr", analyze_pr_node)
    graph.add_node("generate_llm_brief", generate_llm_brief_node)
    graph.add_node("compute_recommendation", compute_recommendation_node)
    graph.add_node("format_output", format_output_node)

    # Define edges — linear flow with a conditional loop
    graph.set_entry_point("fetch_pr_data")
    graph.add_edge("fetch_pr_data", "summarize_pr")
    graph.add_edge("summarize_pr", "search_notion")
    graph.add_edge("search_notion", "score_relevance")
    graph.add_edge("score_relevance", "confirm_context")

    # Conditional: after user confirms context
    graph.add_conditional_edges(
        "confirm_context",
        after_context_confirmation,
        {
            "analyze_pr": "analyze_pr",
            "fetch_specific_page": "fetch_specific_page",
            "search_notion": "search_notion",
            "exit_with_instructions": "exit_with_instructions",
        },
    )

    # fetch_specific_page loops back to confirm_context
    graph.add_edge("fetch_specific_page", "confirm_context")

    # exit_with_instructions → END
    graph.add_edge("exit_with_instructions", END)

    # Main analysis pipeline
    graph.add_edge("analyze_pr", "generate_llm_brief")
    graph.add_edge("generate_llm_brief", "compute_recommendation")
    graph.add_edge("compute_recommendation", "format_output")
    graph.add_edge("format_output", END)

    return graph.compile()
