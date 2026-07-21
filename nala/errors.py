"""The only sanctioned way to catch an exception in the action path.

loud_failure logs a level='error' events row (cause + exception class) before
re-raising, so the caller can convert it into a terminal processed_actions
state and a spoken/printed failure. Bare `except:` is banned in nala/ — see
scripts/lint_action_path.sh."""

from contextlib import contextmanager
from pathlib import Path

from nala import events


@contextmanager
def loud_failure(session_id: str, turn_id: str, context: str, data_dir: Path | None = None):
    try:
        yield
    except Exception as exc:
        events.log_event(
            session_id, turn_id, "error",
            {"context": context, "exception": type(exc).__name__, "message": str(exc)},
            level="error", data_dir=data_dir,
        )
        raise
