import agentdiff


@agentdiff.tool
def web_search(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"


@agentdiff.tool
def get_date() -> str:
    """Get the current date."""
    from datetime import date
    return str(date.today())
