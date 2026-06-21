from agent import research_agent


def main() -> None:
    """Entry point for the sample agent application."""
    result = research_agent("What is quantum computing?")
    print(result)


if __name__ == "__main__":
    main()
