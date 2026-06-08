"""Concrete Python API modules for workflow and tool authoring.

Import user-facing symbols from the concrete modules so the API boundaries stay
visible:

``sophios.apis.python.workflow``
    Graph construction with ``Step`` and ``Workflow``.

``sophios.apis.python.tool_builder``
    CWL ``CommandLineTool`` authoring helpers.
"""

from importlib import import_module
from types import ModuleType


__all__ = ["tool_builder", "workflow"]


def __getattr__(name: str) -> ModuleType:
    if name in __all__:
        return import_module(f".{name}", __name__)
    raise AttributeError(
        f"module {__name__!r} exposes concrete modules only; "
        "import symbols from sophios.apis.python.workflow or "
        "sophios.apis.python.tool_builder"
    )


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
