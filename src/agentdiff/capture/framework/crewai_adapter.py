from agentdiff.capture.framework.base import PatchRegistry, object_name, span_wrapper

_PATCHES = PatchRegistry("crewai")


def install() -> None:
    Crew = _import_attr("crewai", "Crew")
    Agent = _import_attr("crewai", "Agent")
    Task = _import_attr("crewai", "Task")

    if Crew is not None:
        for method_name in ("kickoff", "kickoff_async", "kickoff_for_each", "kickoff_for_each_async"):
            _PATCHES.patch_method(Crew, method_name, _span("crew_kickoff"))
    if Agent is not None:
        for method_name in ("execute_task", "execute_task_async"):
            _PATCHES.patch_method(Agent, method_name, _span("agent_task"))
    if Task is not None:
        for method_name in ("execute", "execute_sync", "execute_async"):
            _PATCHES.patch_method(Task, method_name, _span("task_execute"))


def uninstall() -> None:
    _PATCHES.uninstall()


def _span(kind: str):
    return span_wrapper(
        framework="crewai",
        kind=kind,
        name_getter=lambda self, _args, _kwargs: object_name(self),
    )


def _import_attr(module_name: str, attr: str):
    try:
        module = __import__(module_name, fromlist=[attr])
        return getattr(module, attr, None)
    except Exception:
        return None
