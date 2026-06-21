"""Day 3 tests: all six new provider parsers + sampling_params passthrough."""
from pathlib import Path

import httpx
import pytest
import respx

import agentdiff
import agentdiff.capture.tracer
from agentdiff.capture.tracer import Tracer
from agentdiff.capture.events import LLMRequestEvent, LLMResponseEvent
from agentdiff.trajectory import Trajectory


@pytest.fixture(autouse=True)
def shims():
    agentdiff.install()
    yield
    agentdiff.uninstall()


def _load_trajectory(path: Path) -> Trajectory:
    return Trajectory.model_validate_json(path.read_text().strip().splitlines()[0])


def _capture(tmp_path, url, request_body, response_json, test_case_id="tc"):
    output = tmp_path / "traces.jsonl"
    with respx.mock() as rmock:
        rmock.post(url).mock(return_value=httpx.Response(200, json=response_json))
        with Tracer(test_case_id, "baseline", {}, output):
            httpx.Client().post(url, json=request_body)
    return _load_trajectory(output)


# ---------------------------------------------------------------------------
# Sampling params passthrough (existing parsers)
# ---------------------------------------------------------------------------

def test_anthropic_sampling_params_passthrough(tmp_path):
    """Previously-dropped keys like stop_sequences and metadata now appear."""
    traj = _capture(
        tmp_path,
        "https://api.anthropic.com/v1/messages",
        {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "hi"}],
            "stop_sequences": ["END"],
            "metadata": {"user_id": "u1"},
        },
        {
            "id": "msg_x",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": "hello"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 2},
        },
    )
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert req.canonical.sampling_params["stop_sequences"] == ["END"]
    assert req.canonical.sampling_params["metadata"] == {"user_id": "u1"}
    assert req.canonical.sampling_params["max_tokens"] == 100
    # Structural fields must NOT appear in sampling_params.
    assert "model" not in req.canonical.sampling_params
    assert "messages" not in req.canonical.sampling_params


def test_openai_sampling_params_passthrough(tmp_path):
    traj = _capture(
        tmp_path,
        "https://api.openai.com/v1/chat/completions",
        {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.9,
            "frequency_penalty": 0.5,
            "logprobs": True,
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        },
    )
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert req.canonical.sampling_params["frequency_penalty"] == 0.5
    assert req.canonical.sampling_params["logprobs"] is True


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"

_GEMINI_REQUEST = {
    "contents": [{"role": "user", "parts": [{"text": "Hello Gemini"}]}],
    "system_instruction": {"parts": [{"text": "Be concise."}]},
    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 100},
}

_GEMINI_RESPONSE = {
    "candidates": [
        {
            "content": {"parts": [{"text": "Hello!"}], "role": "model"},
            "finishReason": "STOP",
        }
    ],
    "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 3, "totalTokenCount": 11},
}


def test_gemini_capture(tmp_path):
    traj = _capture(tmp_path, _GEMINI_URL, _GEMINI_REQUEST, _GEMINI_RESPONSE, "tc_gemini")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "gemini"
    assert req.canonical.model == "gemini-pro"
    assert req.canonical.system == "Be concise."
    assert req.canonical.messages == [{"role": "user", "content": "Hello Gemini"}]
    assert req.canonical.sampling_params.get("generationConfig") == {"temperature": 0.7, "maxOutputTokens": 100}

    assert resp.canonical.response_text == "Hello!"
    assert resp.canonical.stop_reason == "STOP"
    assert resp.canonical.usage["input_tokens"] == 8
    assert resp.canonical.usage["output_tokens"] == 3
    assert resp.canonical.usage["total_tokens"] == 11


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------

_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

_MISTRAL_REQUEST = {
    "model": "mistral-large-latest",
    "messages": [{"role": "user", "content": "Hello Mistral"}],
    "temperature": 0.5,
    "safe_prompt": True,
}

_MISTRAL_RESPONSE = {
    "id": "cmpl-xxx",
    "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
}


def test_mistral_capture(tmp_path):
    traj = _capture(tmp_path, _MISTRAL_URL, _MISTRAL_REQUEST, _MISTRAL_RESPONSE, "tc_mistral")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "mistral"
    assert req.canonical.model == "mistral-large-latest"
    assert req.canonical.sampling_params["temperature"] == 0.5
    assert req.canonical.sampling_params["safe_prompt"] is True

    assert resp.canonical.response_text == "Hello!"
    assert resp.canonical.stop_reason == "stop"
    assert resp.canonical.usage["total_tokens"] == 10


# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

_AZURE_URL = "https://my-resource.openai.azure.com/openai/deployments/gpt-4/chat/completions"

_AZURE_REQUEST = {
    "messages": [{"role": "user", "content": "Hello Azure"}],
    "temperature": 0.3,
}

_AZURE_RESPONSE = {
    "model": "gpt-4",
    "choices": [{"message": {"role": "assistant", "content": "Hello from Azure!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 6, "completion_tokens": 5, "total_tokens": 11},
}


def test_azure_openai_capture(tmp_path):
    traj = _capture(tmp_path, _AZURE_URL, _AZURE_REQUEST, _AZURE_RESPONSE, "tc_azure")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "azure_openai"
    assert req.canonical.model == "gpt-4"  # extracted from URL deployment
    assert resp.canonical.response_text == "Hello from Azure!"
    assert resp.canonical.usage["total_tokens"] == 11


# ---------------------------------------------------------------------------
# Bedrock (Anthropic model)
# ---------------------------------------------------------------------------

_BEDROCK_URL = "https://bedrock-runtime.us-east-1.amazonaws.com/model/anthropic.claude-v2/invoke"

_BEDROCK_REQUEST = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 200,
    "messages": [{"role": "user", "content": "Hello Bedrock"}],
}

_BEDROCK_RESPONSE = {
    "id": "msg_bedrock",
    "type": "message",
    "role": "assistant",
    "model": "anthropic.claude-v2",
    "content": [{"type": "text", "text": "Hello from Bedrock!"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


def test_bedrock_anthropic_capture(tmp_path):
    traj = _capture(tmp_path, _BEDROCK_URL, _BEDROCK_REQUEST, _BEDROCK_RESPONSE, "tc_bedrock")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "bedrock"
    assert req.canonical.model == "anthropic.claude-v2"
    assert resp.canonical.response_text == "Hello from Bedrock!"
    assert resp.canonical.stop_reason == "end_turn"
    assert resp.canonical.usage["total_tokens"] == 15


# ---------------------------------------------------------------------------
# Cohere
# ---------------------------------------------------------------------------

_COHERE_URL = "https://api.cohere.com/v1/chat"

_COHERE_REQUEST = {
    "model": "command-r-plus",
    "messages": [{"role": "user", "content": "Hello Cohere"}],
    "max_tokens": 150,
    "temperature": 0.4,
}

_COHERE_RESPONSE = {
    "id": "cohere-resp-1",
    "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello from Cohere!"}],
    },
    "finish_reason": "COMPLETE",
    "usage": {
        "tokens": {"input_tokens": 9, "output_tokens": 6},
    },
}


def test_cohere_capture(tmp_path):
    traj = _capture(tmp_path, _COHERE_URL, _COHERE_REQUEST, _COHERE_RESPONSE, "tc_cohere")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "cohere"
    assert req.canonical.model == "command-r-plus"
    assert req.canonical.sampling_params["max_tokens"] == 150
    assert req.canonical.sampling_params["temperature"] == 0.4

    assert resp.canonical.response_text == "Hello from Cohere!"
    assert resp.canonical.stop_reason == "COMPLETE"
    assert resp.canonical.usage["input_tokens"] == 9
    assert resp.canonical.usage["output_tokens"] == 6


# ---------------------------------------------------------------------------
# OpenAI Responses API
# ---------------------------------------------------------------------------

_RESPONSES_URL = "https://api.openai.com/v1/responses"

_RESPONSES_REQUEST = {
    "model": "gpt-4o",
    "input": "What is 2+2?",
    "instructions": "Be concise.",
    "temperature": 0.1,
}

_RESPONSES_RESPONSE = {
    "id": "resp_abc",
    "model": "gpt-4o",
    "output": [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "4"}],
        }
    ],
    "usage": {"input_tokens": 12, "output_tokens": 2, "total_tokens": 14},
}


def test_openai_responses_capture(tmp_path):
    traj = _capture(tmp_path, _RESPONSES_URL, _RESPONSES_REQUEST, _RESPONSES_RESPONSE, "tc_responses")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "openai_responses"
    assert req.canonical.model == "gpt-4o"
    assert req.canonical.system == "Be concise."
    assert req.canonical.messages == [{"role": "user", "content": "What is 2+2?"}]
    assert req.canonical.sampling_params["temperature"] == 0.1

    assert resp.canonical.response_text == "4"
    assert resp.canonical.usage["total_tokens"] == 14


def test_openai_responses_list_input(tmp_path):
    """Responses API with input as a list of message objects."""
    traj = _capture(
        tmp_path,
        _RESPONSES_URL,
        {
            "model": "gpt-4o",
            "input": [{"role": "user", "content": "Hello"}],
        },
        {
            "model": "gpt-4o",
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi"}]}],
            "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
        },
    )
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert req.canonical.messages == [{"role": "user", "content": "Hello"}]


# ---------------------------------------------------------------------------
# Cohere .ai domain
# ---------------------------------------------------------------------------

def test_cohere_ai_domain(tmp_path):
    traj = _capture(
        tmp_path,
        "https://api.cohere.ai/v1/chat",
        _COHERE_REQUEST,
        _COHERE_RESPONSE,
        "tc_cohere_ai",
    )
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    assert req.canonical.provider == "cohere"


# ---------------------------------------------------------------------------
# Gemini streaming endpoint
# ---------------------------------------------------------------------------

_GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:streamGenerateContent"
)

def test_gemini_stream_url_classified_as_gemini():
    from agentdiff.capture.http.provider_registry import match_provider
    assert match_provider(_GEMINI_STREAM_URL) == "gemini"


def test_gemini_streaming_capture(tmp_path):
    """streamGenerateContent with newline-delimited JSON body is parsed correctly."""
    import json as _json
    chunks = [
        {"candidates": [{"content": {"parts": [{"text": "Hello "}], "role": "model"}}]},
        {
            "candidates": [{"content": {"parts": [{"text": "world!"}], "role": "model"}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8},
        },
    ]
    streaming_body = "\n".join(_json.dumps(c) for c in chunks).encode()

    output = tmp_path / "traces.jsonl"
    with respx.mock() as rmock:
        rmock.post(_GEMINI_STREAM_URL).mock(
            return_value=httpx.Response(200, content=streaming_body)
        )
        with agentdiff.capture.tracer.Tracer("tc_gemini_stream", "baseline", {}, output):
            httpx.Client().post(_GEMINI_STREAM_URL, json=_GEMINI_REQUEST)

    traj = _load_trajectory(output)
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert resp.canonical.provider == "gemini"
    assert resp.canonical.response_text == "Hello world!"
    assert resp.canonical.stop_reason == "STOP"
    assert resp.canonical.usage["input_tokens"] == 5
    assert resp.canonical.usage["output_tokens"] == 3
    assert resp.canonical.usage["total_tokens"] == 8


def test_gemini_streaming_json_array_body(tmp_path):
    """Some clients deliver a streaming response as a JSON array."""
    import json as _json
    chunks = [
        {"candidates": [{"content": {"parts": [{"text": "Hi!"}], "role": "model"}, "finishReason": "STOP"}],
         "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1, "totalTokenCount": 3}},
    ]
    array_body = _json.dumps(chunks).encode()

    output = tmp_path / "traces.jsonl"
    with respx.mock() as rmock:
        rmock.post(_GEMINI_STREAM_URL).mock(
            return_value=httpx.Response(200, content=array_body)
        )
        with agentdiff.capture.tracer.Tracer("tc_gemini_array", "baseline", {}, output):
            httpx.Client().post(_GEMINI_STREAM_URL, json=_GEMINI_REQUEST)

    traj = _load_trajectory(output)
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))
    assert resp.canonical.response_text == "Hi!"


# ---------------------------------------------------------------------------
# Bedrock non-Anthropic model families
# ---------------------------------------------------------------------------

_BEDROCK_BASE = "https://bedrock-runtime.us-east-1.amazonaws.com/model/{model}/invoke"


def test_bedrock_titan_text(tmp_path):
    url = _BEDROCK_BASE.format(model="amazon.titan-text-express-v1")
    req_body = {
        "inputText": "Hello Titan",
        "textGenerationConfig": {"maxTokenCount": 100, "temperature": 0.7},
    }
    resp_body = {
        "inputTextTokenCount": 8,
        "results": [{"tokenCount": 5, "outputText": "Hello from Titan!", "completionReason": "FINISH"}],
    }
    traj = _capture(tmp_path, url, req_body, resp_body, "tc_titan")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.provider == "bedrock"
    assert req.canonical.model == "amazon.titan-text-express-v1"
    assert req.canonical.messages == [{"role": "user", "content": "Hello Titan"}]
    assert resp.canonical.response_text == "Hello from Titan!"
    assert resp.canonical.stop_reason == "FINISH"
    assert resp.canonical.usage["input_tokens"] == 8
    assert resp.canonical.usage["output_tokens"] == 5


def test_bedrock_nova(tmp_path):
    url = _BEDROCK_BASE.format(model="amazon.nova-pro-v1:0")
    req_body = {
        "messages": [{"role": "user", "content": [{"text": "Hello Nova"}]}],
        "system": [{"text": "Be helpful."}],
        "inferenceConfig": {"maxTokens": 200},
    }
    resp_body = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Hello from Nova!"}],
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 6},
    }
    traj = _capture(tmp_path, url, req_body, resp_body, "tc_nova")
    req = next(e for e in traj.events if isinstance(e, LLMRequestEvent))
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert req.canonical.system == "Be helpful."
    assert req.canonical.messages == [{"role": "user", "content": "Hello Nova"}]
    assert resp.canonical.response_text == "Hello from Nova!"
    assert resp.canonical.stop_reason == "end_turn"
    assert resp.canonical.usage["total_tokens"] == 16


def test_bedrock_llama(tmp_path):
    url = _BEDROCK_BASE.format(model="meta.llama3-8b-instruct-v1:0")
    req_body = {"prompt": "Hello Llama", "max_gen_len": 256, "temperature": 0.5}
    resp_body = {
        "generation": "Hello from Llama!",
        "prompt_token_count": 7,
        "generation_token_count": 4,
        "stop_reason": "stop",
    }
    traj = _capture(tmp_path, url, req_body, resp_body, "tc_llama")
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert resp.canonical.response_text == "Hello from Llama!"
    assert resp.canonical.stop_reason == "stop"
    assert resp.canonical.usage["input_tokens"] == 7
    assert resp.canonical.usage["output_tokens"] == 4


def test_bedrock_mistral(tmp_path):
    url = _BEDROCK_BASE.format(model="mistral.mistral-large-2402-v1:0")
    req_body = {"prompt": "<s>[INST] Hello Mistral [/INST]", "max_tokens": 256}
    resp_body = {"outputs": [{"text": "Hello from Mistral!", "stop_reason": "stop"}]}
    traj = _capture(tmp_path, url, req_body, resp_body, "tc_mistral_bedrock")
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert resp.canonical.response_text == "Hello from Mistral!"
    assert resp.canonical.stop_reason == "stop"


def test_bedrock_cohere(tmp_path):
    url = _BEDROCK_BASE.format(model="cohere.command-r-v1:0")
    req_body = {"prompt": "Hello Cohere", "max_tokens": 100}
    resp_body = {"generations": [{"text": "Hello from Cohere!", "finish_reason": "COMPLETE"}]}
    traj = _capture(tmp_path, url, req_body, resp_body, "tc_cohere_bedrock")
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert resp.canonical.response_text == "Hello from Cohere!"
    assert resp.canonical.stop_reason == "COMPLETE"


def test_bedrock_ai21(tmp_path):
    url = _BEDROCK_BASE.format(model="ai21.j2-ultra-v1")
    req_body = {"prompt": "Hello AI21", "maxTokens": 200}
    resp_body = {
        "completions": [
            {"data": {"text": "Hello from AI21!"}, "finishReason": {"reason": "length"}}
        ]
    }
    traj = _capture(tmp_path, url, req_body, resp_body, "tc_ai21")
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert resp.canonical.response_text == "Hello from AI21!"
    assert resp.canonical.stop_reason == "length"


def test_bedrock_generic_unknown_model(tmp_path):
    """Unknown model family gets best-effort text extraction."""
    url = _BEDROCK_BASE.format(model="writer.palmyra-x-004")
    req_body = {"prompt": "Hello"}
    resp_body = {"generation": "Hello from Writer!"}  # Llama-style field
    traj = _capture(tmp_path, url, req_body, resp_body, "tc_bedrock_generic")
    resp = next(e for e in traj.events if isinstance(e, LLMResponseEvent))

    assert resp.canonical.response_text == "Hello from Writer!"
