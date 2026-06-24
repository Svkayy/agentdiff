"""In-process tools. `@agentdiff.tool` makes each call observable to AgentDiff."""
import agentdiff


@agentdiff.tool
def web_search(query: str) -> str:
    """Stand-in web search. Returns canned text so the demo needs no network."""
    return f"[search results for: {query}]"


@agentdiff.tool
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression (used as a confidence score)."""
    try:
        return str(round(eval(expression, {"__builtins__": {}}), 3))  # noqa: S307 — demo only
    except Exception:
        return "0"
