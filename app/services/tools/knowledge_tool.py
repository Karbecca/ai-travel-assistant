from langchain_core.tools import tool

from app.services import knowledge_base


@tool
def knowledge_tool(query: str) -> str:
    """Search the travel knowledge base for curated destination information."""
    try:
        hits = knowledge_base.search(query, n_results=3, destination_filter="")
    except Exception:
        return "Knowledge base unavailable."

    if not hits:
        return "No relevant knowledge found."

    return "\n".join(f"- [{h['title']}] {h['content']}" for h in hits)
