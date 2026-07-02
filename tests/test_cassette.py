import httpx
import pytest
import respx

import agentdiff
from agentdiff.capture.cassette import CassetteMissError, CassetteSchemaError
from agentdiff.capture.tracer import Tracer
from agentdiff.storage import load_trajectory_set


@pytest.fixture(autouse=True)
def shims():
    agentdiff.install()
    yield
    agentdiff.uninstall()


def test_httpx_cassette_records_and_replays_without_network(tmp_path):
    cassette_path = tmp_path / "http.jsonl"
    record_output = tmp_path / "record.jsonl"
    replay_output = tmp_path / "replay.jsonl"
    url = "https://api.openai.com/v1/chat/completions"
    request_body = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]}
    response_body = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    with respx.mock() as rmock:
        rmock.post(url).mock(return_value=httpx.Response(200, json=response_body))
        with agentdiff.cassette(cassette_path, "record"):
            with Tracer("tc", "baseline", {}, record_output):
                resp = httpx.post(url, json=request_body)
                assert resp.json()["choices"][0]["message"]["content"] == "Hello"

    assert cassette_path.read_text(encoding="utf-8").strip()

    with respx.mock(assert_all_called=False) as rmock:
        rmock.post(url).mock(side_effect=AssertionError("network should not be called"))
        with agentdiff.cassette(cassette_path, "replay"):
            with Tracer("tc", "candidate", {}, replay_output):
                resp = httpx.post(url, json=request_body)
                assert resp.json()["choices"][0]["message"]["content"] == "Hello"

    replay_set = load_trajectory_set(replay_output, "candidate")
    assert len(replay_set.trajectories) == 1
    events = replay_set.trajectories[0].events
    assert [event.event_type for event in events] == ["llm_request", "llm_response"]
    assert events[1].canonical.response_text == "Hello"


def test_cassette_miss_fails_loud(tmp_path):
    cassette_path = tmp_path / "empty.jsonl"
    cassette_path.write_text("", encoding="utf-8")
    with agentdiff.cassette(cassette_path, "replay"):
        with pytest.raises(CassetteMissError, match="no cassette recording"):
            with Tracer("tc", "candidate", {}, tmp_path / "out.jsonl"):
                httpx.post("https://api.openai.com/v1/chat/completions", json={"model": "gpt-4o"})


def test_cassette_schema_error_fails_loud(tmp_path):
    cassette_path = tmp_path / "bad.jsonl"
    cassette_path.write_text('{"schema_version": 999}\n', encoding="utf-8")
    with pytest.raises(CassetteSchemaError, match="unsupported cassette schema"):
        with agentdiff.cassette(cassette_path, "replay"):
            pass
