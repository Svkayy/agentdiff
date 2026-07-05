from agentdiff.capture.framework import (
    autogen_adapter,
    crewai_adapter,
    langgraph_adapter,
    llamaindex_adapter,
)

_ADAPTERS = {
    "langgraph": langgraph_adapter,
    "crewai": crewai_adapter,
    "autogen": autogen_adapter,
    "llamaindex": llamaindex_adapter,
}


def install(capture: dict[str, bool] | None = None) -> list[str]:
    """Install enabled framework adapters. Returns names enabled but unavailable."""
    capture = capture or {}
    unavailable = []
    for name, adapter in _ADAPTERS.items():
        if capture.get(name, True) and not adapter.install():
            unavailable.append(name)
    return unavailable


def uninstall() -> None:
    for adapter in reversed(list(_ADAPTERS.values())):
        adapter.uninstall()
