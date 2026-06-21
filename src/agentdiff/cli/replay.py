import click


@click.command("replay")
def replay_cmd() -> None:
    """Replay captured tool calls (stub in v0).

    v0 always executes tools live during sampling. ReplaySession-based replay
    lands in v1.
    """
    click.echo("agentdiff replay: not implemented in v0.")
