import anthropic

client = anthropic.Anthropic()


def research_agent(query: str) -> str:
    """Agent that answers questions using Claude."""
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": query}],
    )
    return response.content[0].text
