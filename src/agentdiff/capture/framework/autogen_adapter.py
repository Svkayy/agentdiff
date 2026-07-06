from agentdiff.capture.framework.base import PatchRegistry, object_name, span_wrapper

_PATCHES = PatchRegistry("autogen")


def install() -> bool:
    """Patch autogen if installed. Returns False if autogen isn't importable."""
    ConversableAgent = _import_attr(
        ("autogen", "ConversableAgent"),
        ("autogen.agentchat", "ConversableAgent"),
    )
    if ConversableAgent is None:
        return False
    for method_name, kind in (
        ("send", "speaker_turn"),
        ("a_send", "speaker_turn"),
        ("receive", "message_receive"),
        ("a_receive", "message_receive"),
        ("generate_reply", "reply_generate"),
        ("a_generate_reply", "reply_generate"),
    ):
        _PATCHES.patch_method(ConversableAgent, method_name, _span(kind))
    return True


def uninstall() -> None:
    _PATCHES.uninstall()


def _span(kind: str):
    return span_wrapper(
        framework="autogen",
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
