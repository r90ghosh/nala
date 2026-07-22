"""Tool registry + the chokepoint's dispatch guard.

M4 replaces the ambient contextvars.ContextVar guard with an explicit,
call-stack-scoped capability: execute_action() mints a single-use
DispatchTicket for the duration of exactly one dispatch and hands it to the
tool directly via tools.dispatch(name, args, ticket) — tools never read
ambient state. This matters because a contextvars.ContextVar is *copied* into
any asyncio.Task spawned while it's set; a task created inside a dispatch
window keeps seeing the guard as "open" forever, even after the window that
spawned it has closed. A DispatchTicket has no such leak: its liveness is a
mutable flag on the ticket object itself, checked at call time, so retiring
it is instantly visible to anyone still holding a reference — including a
task that outlived the window that created it."""

from contextlib import contextmanager

TOOLS: dict[str, callable] = {}


class ToolInvokedOutsideChokepoint(RuntimeError):
    """Raised when a tool function is called without a live DispatchTicket."""


class DispatchTicket:
    """Opaque, single-use capability minted by execute_action() for the
    duration of one dispatch. Passed to tools explicitly — never ambient,
    never inherited by a spawned task the way a contextvar would be."""

    __slots__ = ("_active",)

    def __init__(self):
        self._active = False

    def _activate(self) -> None:
        self._active = True

    def _retire(self) -> None:
        self._active = False

    def is_active(self) -> bool:
        return self._active


def assert_valid_ticket(ticket) -> None:
    if not isinstance(ticket, DispatchTicket) or not ticket.is_active():
        raise ToolInvokedOutsideChokepoint(
            "tools may only be invoked via nala.chokepoint.execute_action(), with a live DispatchTicket"
        )


@contextmanager
def dispatching():
    """Mint a ticket, activate it for the duration of the with-block, retire
    it on exit — success or failure — so it can never be used again."""
    ticket = DispatchTicket()
    ticket._activate()
    try:
        yield ticket
    finally:
        ticket._retire()


def register(action_type: str):
    def deco(fn):
        TOOLS[action_type] = fn
        return fn
    return deco


def dispatch(action_type: str, args: dict, ticket: DispatchTicket):
    """The only sanctioned way to call a tool: explicit ticket in hand."""
    return TOOLS[action_type](**args, ticket=ticket)


# Import submodules to populate the registry — after the helpers above are
# defined, since each submodule imports assert_valid_ticket/register from us.
from nala.tools import capture_task as _capture_task  # noqa: E402,F401
from nala.tools import report_status as _report_status  # noqa: E402,F401
from nala.tools import archive_task as _archive_task  # noqa: E402,F401
