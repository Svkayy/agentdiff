"""AgentDiff Runner — one observable invocation of the agent per test case."""
from agents.orchestrator import run_research


def run(input: dict) -> str:
    return run_research(input["query"])


def main() -> None:
    print(run({"query": "What is the capital of France?"}))


if __name__ == "__main__":
    main()
