"""Retriever sub-agent — gathers source material, then summarizes it."""
from agents.llm import chat
from tools import web_search


def retriever_agent(query: str) -> str:
    results = web_search(query)
    return chat(f"Summarize what these search results say about '{query}':\n{results}")
