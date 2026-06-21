from agentdiff.capture.framework import registry as framework_registry
from agentdiff.capture.http import aiohttp_shim, httpx_shim, requests_shim
from agentdiff.capture.rpc import grpc_shim
from agentdiff.capture.sdk import anthropic_shim, openai_shim, mcp_shim


def install(capture: dict[str, bool] | None = None) -> None:
    capture = capture or {}
    if capture.get("httpx", True):
        httpx_shim.install()
    if capture.get("requests", True):
        requests_shim.install()
    if capture.get("aiohttp", True):
        aiohttp_shim.install()
    if capture.get("grpc", True):
        grpc_shim.install()
    if capture.get("anthropic_sdk", True):
        anthropic_shim.install()
    if capture.get("openai_sdk", True):
        openai_shim.install()
    if capture.get("mcp", True):
        mcp_shim.install()
    framework_registry.install(capture)


def uninstall() -> None:
    mcp_shim.uninstall()
    openai_shim.uninstall()
    anthropic_shim.uninstall()
    framework_registry.uninstall()
    grpc_shim.uninstall()
    aiohttp_shim.uninstall()
    requests_shim.uninstall()
    httpx_shim.uninstall()
