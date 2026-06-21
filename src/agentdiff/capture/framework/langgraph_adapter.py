import functools
import inspect
from typing import Any

from agentdiff.capture.framework.base import (
    PatchRegistry,
    call_metadata,
    object_name,
    record_framework_event,
    span_wrapper,
)

_PATCHES = PatchRegistry("langgraph")


def install() -> None:
    """Install best-effort LangGraph graph/node capture."""
    _patch_pregel()
    _patch_state_graph()


def uninstall() -> None:
    _PATCHES.uninstall()


def _patch_pregel() -> None:
    Pregel = _import_attr(
        ("langgraph.pregel", "Pregel"),
        ("langgraph.pregel.main", "Pregel"),
    )
    if Pregel is None:
        return
    for method_name in ("invoke", "ainvoke"):
        _PATCHES.patch_method(
            Pregel,
            method_name,
            span_wrapper(
                framework="langgraph",
                kind="graph_invoke",
                name_getter=lambda self, _args, _kwargs: object_name(self, "graph"),
            ),
        )


def _patch_state_graph() -> None:
    StateGraph = _import_attr(
        ("langgraph.graph", "StateGraph"),
        ("langgraph.graph.state", "StateGraph"),
    )
    if StateGraph is None:
        return
    _PATCHES.patch_method(StateGraph, "add_node", _wrap_add_node)
    _PATCHES.patch_method(StateGraph, "add_edge", _wrap_add_edge)
    _PATCHES.patch_method(StateGraph, "add_conditional_edges", _wrap_add_conditional_edges)


def _wrap_add_node(original):
    @functools.wraps(original)
    def wrapper(self, node, action=None, *args, **kwargs):
        node_name = _node_name(node, action)
        if action is None and callable(node) and not isinstance(node, str):
            node = _wrap_node_callable(node, node_name)
        elif callable(action):
            action = _wrap_node_callable(action, node_name)
        elif "action" in kwargs and callable(kwargs["action"]):
            kwargs["action"] = _wrap_node_callable(kwargs["action"], node_name)
        return original(self, node, action, *args, **kwargs)

    return wrapper


def _wrap_add_edge(original):
    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        record_framework_event(
            framework="langgraph",
            kind="edge_registered",
            name="->".join(str(a) for a in args[:2]) if len(args) >= 2 else None,
            metadata={**call_metadata(args, kwargs), "edge_args": [str(a) for a in args[:3]]},
            skip=2,
        )
        return original(self, *args, **kwargs)

    return wrapper


def _wrap_add_conditional_edges(original):
    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        record_framework_event(
            framework="langgraph",
            kind="conditional_edges_registered",
            name=str(args[0]) if args else None,
            metadata=call_metadata(args, kwargs),
            skip=2,
        )
        return original(self, *args, **kwargs)

    return wrapper


def _wrap_node_callable(fn, node_name: str | None):
    if getattr(fn, "_agentdiff_langgraph_node", False):
        return fn

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_node(*args, **kwargs):
            call_id = record_framework_event(
                framework="langgraph",
                kind="node_start",
                name=node_name or getattr(fn, "__name__", None),
                metadata=call_metadata(args, kwargs),
                skip=2,
            )
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                record_framework_event(
                    framework="langgraph",
                    kind="node_end",
                    name=node_name or getattr(fn, "__name__", None),
                    metadata={"is_error": True, "error": repr(exc)},
                    call_id=call_id,
                    skip=2,
                )
                raise
            record_framework_event(
                framework="langgraph",
                kind="node_end",
                name=node_name or getattr(fn, "__name__", None),
                metadata={"is_error": False},
                call_id=call_id,
                skip=2,
            )
            return result

        setattr(async_node, "_agentdiff_langgraph_node", True)
        return async_node

    @functools.wraps(fn)
    def sync_node(*args, **kwargs):
        call_id = record_framework_event(
            framework="langgraph",
            kind="node_start",
            name=node_name or getattr(fn, "__name__", None),
            metadata=call_metadata(args, kwargs),
            skip=2,
        )
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            record_framework_event(
                framework="langgraph",
                kind="node_end",
                name=node_name or getattr(fn, "__name__", None),
                metadata={"is_error": True, "error": repr(exc)},
                call_id=call_id,
                skip=2,
            )
            raise
        record_framework_event(
            framework="langgraph",
            kind="node_end",
            name=node_name or getattr(fn, "__name__", None),
            metadata={"is_error": False},
            call_id=call_id,
            skip=2,
        )
        return result

    setattr(sync_node, "_agentdiff_langgraph_node", True)
    return sync_node


def _node_name(node: Any, action: Any) -> str | None:
    if isinstance(node, str):
        return node
    for obj in (action, node):
        name = getattr(obj, "__name__", None)
        if name:
            return str(name)
    return None


def _import_attr(*choices: tuple[str, str]):
    for module_name, attr in choices:
        try:
            module = __import__(module_name, fromlist=[attr])
            return getattr(module, attr, None)
        except Exception:
            continue
    return None
