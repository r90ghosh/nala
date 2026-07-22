"""Spend ledger + daily ceiling. Rates in USD per million tokens."""

from datetime import datetime, timezone
from pathlib import Path

from nala.config import get_daily_ceiling
from nala.db import connect

RATES = {
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
    "llama3.2:3b": {"input": 0.0, "output": 0.0},  # local via Ollama — free, but ledgered so the record stays complete
}


class SpendCeilingExceeded(Exception):
    pass


def _connect(data_dir: Path | None = None):
    conn = connect(data_dir)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spend (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            turn_id TEXT,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            est_cost_usd REAL NOT NULL,
            day TEXT NOT NULL
        )
        """
    )
    return conn


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = RATES.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]


def record_spend(
    turn_id: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    data_dir: Path | None = None,
) -> float:
    cost = estimate_cost(model, input_tokens, output_tokens)
    now = datetime.now(timezone.utc)
    conn = _connect(data_dir)
    conn.execute(
        "INSERT INTO spend (ts, turn_id, model, input_tokens, output_tokens, est_cost_usd, day) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (now.isoformat(), turn_id, model, input_tokens, output_tokens, cost, now.date().isoformat()),
    )
    conn.commit()
    conn.close()
    return cost


def today_total(data_dir: Path | None = None) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    conn = _connect(data_dir)
    row = conn.execute("SELECT COALESCE(SUM(est_cost_usd), 0) AS total FROM spend WHERE day = ?", (today,)).fetchone()
    conn.close()
    return row["total"]


def check_ceiling(data_dir: Path | None = None) -> None:
    ceiling = get_daily_ceiling()
    total = today_total(data_dir)
    if total >= ceiling:
        raise SpendCeilingExceeded(f"daily spend ${total:.4f} has reached the ${ceiling:.2f} ceiling")
