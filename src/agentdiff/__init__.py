from agentdiff.capture.activator import install as _install, uninstall as _uninstall
from agentdiff.capture.decorators import tool
from agentdiff.capture.session import record

__version__ = "0.1.0"

_INSTALLED = False
_INSTALLED_CONFIG: dict[str, bool] | None = None


def install(capture: dict[str, bool] | None = None) -> None:
    """Install all capture shims. Idempotent."""
    global _INSTALLED, _INSTALLED_CONFIG
    capture = capture or {}
    if _INSTALLED:
        if capture == (_INSTALLED_CONFIG or {}):
            return
        _uninstall()
        _INSTALLED = False
    _install(capture)
    _INSTALLED = True
    _INSTALLED_CONFIG = dict(capture)


def uninstall() -> None:
    """Remove all capture shims."""
    global _INSTALLED, _INSTALLED_CONFIG
    if not _INSTALLED:
        return
    _uninstall()
    _INSTALLED = False
    _INSTALLED_CONFIG = None


__all__ = ["install", "uninstall", "tool", "record"]
