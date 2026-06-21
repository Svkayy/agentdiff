"""Recipe A — Request-response.

The simplest shape: your agent's existing entry function *is* the Runner.
AgentDiff calls run(input) once per sample with capture active, and stores the
returned string as the trajectory's final_output.

Point .agentdiff/config.yaml at this module:

    runner:
      module: docs.recipes.request_response
      callable: run
"""
# Replace this import with your agent's real entry function.
from my_app.handlers import handle_query


def run(input: dict) -> str:
    # `input` is whatever you put under `input:` in test_cases.yaml.
    return handle_query(input["query"])
