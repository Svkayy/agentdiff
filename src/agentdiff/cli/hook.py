import click
from rich.console import Console

from agentdiff.cli.init import (
    autoload_hook_installed,
    autoload_pth_path,
    install_autoload_hook,
    uninstall_autoload_hook,
)

console = Console()


@click.group("hook")
def hook_cmd() -> None:
    """Manage AgentDiff's optional startup capture hook."""


@hook_cmd.command("status")
def hook_status_cmd() -> None:
    """Show whether the autoload hook is installed in this environment."""
    pth = autoload_pth_path()
    if autoload_hook_installed():
        console.print(f"[green]Installed[/green] → {pth}")
    else:
        console.print(f"[yellow]Not installed[/yellow] → {pth}")


@hook_cmd.command("install")
def hook_install_cmd() -> None:
    """Install the autoload hook for this Python environment."""
    pth = install_autoload_hook()
    if pth is None:
        console.print("[red]Could not install AgentDiff's autoload hook.[/red]")
        raise SystemExit(1)
    console.print(f"[green]Installed[/green] → {pth}")


@hook_cmd.command("uninstall")
def hook_uninstall_cmd() -> None:
    """Remove the autoload hook from this Python environment."""
    pth = autoload_pth_path()
    if uninstall_autoload_hook():
        console.print(f"[green]Removed[/green] → {pth}")
    else:
        console.print(f"[yellow]No AgentDiff hook found[/yellow] → {pth}")
