"""Recipe D — Multi-turn conversational.

For chat agents where one "invocation" is a scripted sequence of user turns. The
Runner drives the whole conversation in one trajectory; every turn's LLM and tool
calls are captured under the same test case as an ordered sequence.

Point .agentdiff/config.yaml at this module:

    runner:
      module: docs.recipes.multi_turn
      callable: run
"""
from my_app.chat import ChatSession


def run(input: dict) -> dict:
    session = ChatSession()
    responses = []
    for turn in input["turns"]:
        if turn["role"] == "user":
            responses.append(session.send(turn["content"]))
    return {
        "final_response": responses[-1] if responses else None,
        "turn_count": len(responses),
        "intermediate_responses": responses,
    }
