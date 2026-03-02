"""Conditional edge functions for the LangGraph workflow."""

from __future__ import annotations

from pr_review_agent.graph.state import AgentState


def after_context_confirmation(state: AgentState) -> str:
    """Route based on user's context confirmation response."""
    choice = state.get("user_confirmation", "exit")

    if choice == "confirmed":
        return "analyze_pr"
    elif choice == "provide_url":
        return "fetch_specific_page"
    elif choice == "partial":
        return "search_notion"
    else:  # "exit"
        return "exit_with_instructions"
