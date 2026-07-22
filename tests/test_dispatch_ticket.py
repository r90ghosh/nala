"""M4 hard precondition: the chokepoint guard is call-stack-scoped (an
explicit DispatchTicket), not an ambient contextvars.ContextVar — which would
leak into any asyncio.Task spawned inside a dispatch window and keep the
guard "open" forever in that task, even after the window that spawned it
closed. These tests reproduce the exact leak the reviewer demonstrated and
prove the fix, plus that tickets are per-dispatch and thread-independent."""

import asyncio
import threading

import pytest

from nala import tools
from nala.tools import ToolInvokedOutsideChokepoint


def test_ticket_is_active_only_inside_its_own_dispatch_window(data_dir):
    with tools.dispatching() as ticket:
        assert ticket.is_active()
    assert not ticket.is_active()


def test_stale_ticket_cannot_be_reused_after_dispatch_ends(data_dir):
    with tools.dispatching() as ticket:
        pass  # window closes here — ticket retired

    with pytest.raises(ToolInvokedOutsideChokepoint):
        tools.dispatch("report_status", {}, ticket)


def test_asyncio_task_spawned_inside_window_cannot_dispatch_after_it_closes(data_dir):
    """The exact leak: a contextvar is copied into a child Task at creation
    time, so a task spawned while the guard was "open" keeps seeing it open
    forever, regardless of what the parent does afterward. A DispatchTicket
    has no such copy — its liveness is the object's own mutable state, so a
    task that tries to use it after the window closed must fail."""
    task_error: dict = {}

    async def leaky_child(ticket):
        # Let the parent's `with` block exit before we try to use the ticket.
        await asyncio.sleep(0.05)
        try:
            tools.dispatch("report_status", {}, ticket)
        except Exception as exc:
            task_error["exc"] = exc

    async def scenario():
        with tools.dispatching() as ticket:
            child = asyncio.create_task(leaky_child(ticket))
        # Window is now closed (ticket retired); the child is still pending.
        await child

    asyncio.run(scenario())

    assert isinstance(task_error.get("exc"), ToolInvokedOutsideChokepoint)


def test_two_overlapping_thread_dispatches_dont_interfere(data_dir):
    b_may_start = threading.Event()
    b_is_active = threading.Event()
    a_finished = threading.Event()
    a_ticket_holder: dict = {}
    b_assertion_error: dict = {}

    def thread_a():
        with tools.dispatching() as ticket:
            a_ticket_holder["ticket"] = ticket
            b_may_start.set()
            b_is_active.wait(timeout=2)
        a_finished.set()  # A's ticket is now retired

    def thread_b():
        b_may_start.wait(timeout=2)
        with tools.dispatching() as ticket:
            b_is_active.set()
            a_finished.wait(timeout=2)
            # A's ticket was just retired — that must not affect B's, which
            # is still inside its own window.
            try:
                assert ticket.is_active()
            except AssertionError as exc:
                b_assertion_error["exc"] = exc

    ta = threading.Thread(target=thread_a)
    tb = threading.Thread(target=thread_b)
    ta.start()
    tb.start()
    ta.join(timeout=5)
    tb.join(timeout=5)

    assert "exc" not in b_assertion_error
    assert not a_ticket_holder["ticket"].is_active()
    with pytest.raises(ToolInvokedOutsideChokepoint):
        tools.dispatch("report_status", {}, a_ticket_holder["ticket"])
