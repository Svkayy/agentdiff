from agentdiff.capture.framework.base import PatchRegistry, object_name, span_wrapper

_PATCHES = PatchRegistry("llamaindex")


def install() -> None:
    BaseQueryEngine = _import_attr(
        ("llama_index.core.base.base_query_engine", "BaseQueryEngine"),
        ("llama_index.core.query_engine", "BaseQueryEngine"),
    )
    BaseRetriever = _import_attr(
        ("llama_index.core.base.base_retriever", "BaseRetriever"),
        ("llama_index.core.retrievers", "BaseRetriever"),
    )
    BaseRouterRetriever = _import_attr(
        ("llama_index.core.retrievers.router_retriever", "RouterRetriever"),
    )

    if BaseQueryEngine is not None:
        for method_name in ("query", "aquery"):
            _PATCHES.patch_method(BaseQueryEngine, method_name, _span("query_engine"))
    if BaseRetriever is not None:
        for method_name in ("retrieve", "aretrieve"):
            _PATCHES.patch_method(BaseRetriever, method_name, _span("retriever"))
    if BaseRouterRetriever is not None:
        for method_name in ("retrieve", "aretrieve"):
            _PATCHES.patch_method(BaseRouterRetriever, method_name, _span("router_retriever"))


def uninstall() -> None:
    _PATCHES.uninstall()


def _span(kind: str):
    return span_wrapper(
        framework="llamaindex",
        kind=kind,
        name_getter=lambda self, _args, _kwargs: object_name(self),
    )


def _import_attr(*choices: tuple[str, str]):
    for module_name, attr in choices:
        try:
            module = __import__(module_name, fromlist=[attr])
            return getattr(module, attr, None)
        except Exception:
            continue
    return None
