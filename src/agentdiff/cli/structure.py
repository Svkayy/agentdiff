import click


@click.command("structure")
def structure_cmd() -> None:
    """Refresh structure.yaml (stub in v0).

    In v0, regenerate structure.yaml by re-running `agentdiff init`. A dedicated
    three-way-diff refresh lands in v1.
    """
    click.echo(
        "agentdiff structure: not implemented in v0. "
        "Re-run `agentdiff init` to regenerate .agentdiff/structure.yaml."
    )
