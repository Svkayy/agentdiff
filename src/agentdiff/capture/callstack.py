import inspect
import site
import sys
from pathlib import Path

from agentdiff.capture.events import CallSite, StackFrame

# Build site-packages paths once at import time.
_SITE_PACKAGES: set[Path] = set()
try:
    for p in site.getsitepackages():
        _SITE_PACKAGES.add(Path(p))
except AttributeError:
    pass
try:
    _SITE_PACKAGES.add(Path(site.getusersitepackages()))
except AttributeError:
    pass

_KNOWN_SDK_SUBSTRINGS = (
    "httpx", "requests", "urllib3", "anthropic", "openai", "mcp",
    "certifi", "h2", "h11", "anyio", "sniffio", "charset_normalizer",
    "aiohttp",
)
_KNOWN_FRAMEWORK_SUBSTRINGS = (
    "langchain", "langgraph", "crewai", "pydantic_ai", "autogen",
    "llama_index", "haystack",
)


def _safe_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _classify_frame(
    filename: str, module_name: str
) -> tuple[bool, bool, bool, bool]:
    """Return (is_user_code, is_sdk_internal, is_framework_internal, is_agentdiff_internal)."""
    if not filename or filename.startswith("<"):
        return False, False, False, False

    # Agentdiff internal by module name (handles both installed and editable).
    if module_name and (
        module_name == "agentdiff" or module_name.startswith("agentdiff.")
    ):
        return False, False, False, True

    fp = Path(filename)
    fn_str = filename.replace("\\", "/")

    # Stdlib: inside Python's prefix/lib but not site-packages.
    for prefix in (sys.prefix, getattr(sys, "base_prefix", sys.prefix)):
        lib = Path(prefix) / "lib"
        if _safe_is_relative_to(fp, lib):
            in_site = any(_safe_is_relative_to(fp, sp) for sp in _SITE_PACKAGES)
            if not in_site:
                return False, False, False, False

    # Site-packages: third-party code.
    in_site = any(_safe_is_relative_to(fp, sp) for sp in _SITE_PACKAGES)
    if in_site:
        for substr in _KNOWN_SDK_SUBSTRINGS:
            if f"/{substr}/" in fn_str or fn_str.endswith(f"/{substr}"):
                return False, True, False, False
        for substr in _KNOWN_FRAMEWORK_SUBSTRINGS:
            if f"/{substr}" in fn_str:
                return False, False, True, False
        # Other third-party package — still not user code.
        return False, True, False, False

    # Everything else is user code.
    return True, False, False, False


def capture_call_stack(skip: int = 0) -> list[StackFrame]:
    """Capture the current Python call stack.

    skip: additional frames to drop from the top beyond this function itself.
    """
    raw = inspect.stack()
    # Always skip this function; caller may skip more of their own frames.
    frames = raw[1 + skip:]

    result = []
    for fi in frames:
        filename = fi.filename or ""
        module_name = fi.frame.f_globals.get("__name__", "") or ""
        is_user, is_sdk, is_fw, is_ad = _classify_frame(filename, module_name)
        result.append(
            StackFrame(
                file=filename,
                function=fi.function,
                line=fi.lineno,
                is_user_code=is_user,
                is_framework_internal=is_fw,
                is_agentdiff_internal=is_ad,
                is_sdk_internal=is_sdk,
            )
        )

    return result


def classify_call_stack(frames: list[StackFrame]) -> str | None:
    """Return the nearest user-code function name, or None."""
    for frame in frames:
        if frame.is_user_code and frame.function and frame.function != "<module>":
            return frame.function
    return None


def callsite_from_stack(frames: list[StackFrame]) -> CallSite:
    """Return the nearest user-code call site, with fallback."""
    for frame in frames:
        if frame.is_user_code:
            return CallSite(file=frame.file, function=frame.function, line=frame.line)
    # Fallback: first non-agentdiff frame.
    for frame in frames:
        if not frame.is_agentdiff_internal:
            return CallSite(file=frame.file, function=frame.function, line=frame.line)
    return CallSite(file="<unknown>", function="<unknown>", line=0)
