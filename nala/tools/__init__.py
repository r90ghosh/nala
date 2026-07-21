"""Tool registry. Every tool asserts it's being dispatched by the chokepoint —
the contextvar below is set only inside chokepoint.execute_action(); a direct
call raises ToolInvokedOutsideChokepoint."""

import contextvars
from contextlib import contextmanager

_dispatching: contextvars.ContextVar[bool] = contextvars.ContextVar("_dispatching", default=False)

TOOLS: dict[str, callable] = {}


class ToolInvokedOutsideChokepoint(RuntimeError):
    """Raised when a tool function is called without going through
    nala.chokepoint.execute_action()."""


def assert_in_chokepoint() -> None:
    if not _dispatching.get():
        raise ToolInvokedOutsideChokepoint(
            "tools may only be invoked via nala.chokepoint.execute_action()"
        )


@contextmanager
def dispatching():
    token = _dispatching.set(True)
    try:
        yield
    finally:
        _dispatching.reset(token)


def register(action_type: str):
    def deco(fn):
        TOOLS[action_type] = fn
        return fn
    return deco


# Import submodules to populate the registry — after the helpers above are
# defined, since each submodule imports assert_in_chokepoint/register from us.
from nala.tools import capture_task as _capture_task  # noqa: E402,F401
from nala.tools import report_status as _report_status  # noqa: E402,F401
from nala.tools import archive_task as _archive_task  # noqa: E402,F401
