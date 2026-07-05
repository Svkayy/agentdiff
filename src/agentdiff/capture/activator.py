import warnings
from typing import Callable

from agentdiff.capture.framework import registry as framework_registry
from agentdiff.capture.http import aiohttp_shim, httpx_shim, requests_shim
from agentdiff.capture.rpc import grpc_shim
from agentdiff.capture.sdk import anthropic_shim, openai_shim, mcp_shim


class AgentDiffCaptureWarning(UserWarning):
    """Raised once per process when an enabled capture shim can't be installed.

    A shim reports "unavailable" (rather than silently no-op'ing) when its
    target library isn't importable — e.g. ``httpx`` enabled in config but not
    installed in the environment. Capture degrading silently would make a
    trajectory look complete when whole categories of calls were never
    recorded, so this is loud by design.
    """


# Framework adapters are handled by framework_registry.install(), which already
# reports per-adapter availability via its own return value.
_SIMPLE_SHIMS: dict[str, Callable[[], bool]] = {
    "httpx": httpx_shim.install,
    "requests": requests_shim.install,
    "aiohttp": aiohttp_shim.install,
    "grpc": grpc_shim.install,
    "anthropic_sdk": anthropic_shim.install,
    "openai_sdk": openai_shim.install,
    "mcp": mcp_shim.install,
}


def install(capture: dict[str, bool] | None = None) -> None:
    capture = capture or {}
    for name, install_shim in _SIMPLE_SHIMS.items():
        if not capture.get(name, True):
            continue
        installed = install_shim()
        if installed is False:
            warnings.warn(
                f"AgentDiff capture: '{name}' is enabled but its library is not "
                "installed — calls made through it will not be recorded. "
                "Install the library, or disable it in .agentdiff/config.yaml "
                f"(capture.{name}: false) to silence this warning.",
                AgentDiffCaptureWarning,
                stacklevel=2,
            )

    unavailable = framework_registry.install(capture)
    for name in unavailable:
        warnings.warn(
            f"AgentDiff capture: '{name}' is enabled but its library is not "
            "installed — calls made through it will not be recorded. "
            "Install the library, or disable it in .agentdiff/config.yaml "
            f"(capture.{name}: false) to silence this warning.",
            AgentDiffCaptureWarning,
            stacklevel=2,
        )


def uninstall() -> None:
    mcp_shim.uninstall()
    openai_shim.uninstall()
    anthropic_shim.uninstall()
    framework_registry.uninstall()
    grpc_shim.uninstall()
    aiohttp_shim.uninstall()
    requests_shim.uninstall()
    httpx_shim.uninstall()
