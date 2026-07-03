import click

from agentdiff.cli.init import init_cmd
from agentdiff.cli.compare import compare_cmd
from agentdiff.cli.ci import ci_cmd
from agentdiff.cli.dashboard import dashboard_cmd
from agentdiff.cli.diff import diff_cmd
from agentdiff.cli.doctor import doctor_cmd
from agentdiff.cli.hook import hook_cmd
from agentdiff.cli.quickstart import quickstart_cmd
from agentdiff.cli.structure import structure_cmd
from agentdiff.cli.replay import replay_cmd
from agentdiff.cli.traffic import traffic_cmd
from agentdiff.cli.monitor import monitor_cmd


@click.group()
def cli() -> None:
    """AgentDiff — behavioral regression testing for AI agent systems."""


cli.add_command(init_cmd)
cli.add_command(compare_cmd)
cli.add_command(ci_cmd)
cli.add_command(dashboard_cmd)
cli.add_command(diff_cmd)
cli.add_command(doctor_cmd)
cli.add_command(hook_cmd)
cli.add_command(quickstart_cmd)
cli.add_command(structure_cmd)
cli.add_command(replay_cmd)
cli.add_command(traffic_cmd)
cli.add_command(monitor_cmd)
