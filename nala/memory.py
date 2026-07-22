"""Graph memory store (~/.nala/memory.db, WAL + busy_timeout like every other
db in this project). Nodes are scoped per-purpose (or 'people' for the
shared core persons live in), edges connect them, and observations are the
actual facts — each one carrying non-negotiable provenance: a source, a
source_ref (the event/message it came from), and a timestamp. There is no
way to record an observation without knowing where it came from; that's
enforced here, not just at the boundary-validation layer above it."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nala.config import get_data_dir

DB_FILENAME = "memory.db"

VALID_KINDS = {"person", "project", "preference", "event", "thing", "place"}
VALID_SOURCES = {"user_said", "gmail", "imessage", "calendar", "triage", "manual"}


class MemoryError(Exception):
    """Invalid memory operation: bad kind/source, a reference to a node_id
    that doesn't exist, or (non-negotiable) missing provenance."""


def connect(data_dir: Path | None = None) -> sqlite3.Connection:
    d = data_dir or get_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(d / DB_FILENAME)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def _dedupe_existing_nodes(conn: sqlite3.Connection) -> None:
    """One-time cleanup so CREATE UNIQUE INDEX below doesn't fail on a
    ~/.nala/memory.db that predates this constraint and — because
    upsert_node used to SELECT-then-INSERT/UPDATE with no atomicity — could
    already have raced its way into genuine duplicates. Keeps the oldest
    node per (kind, label, purpose_scope), reassigns any observations/edges
    pointing at the duplicates to the survivor, then deletes the losers."""
    dupes = conn.execute(
        "SELECT kind, label, purpose_scope, GROUP_CONCAT(node_id) AS ids "
        "FROM nodes GROUP BY kind, label, purpose_scope HAVING COUNT(*) > 1"
    ).fetchall()
    for row in dupes:
        ids = row["ids"].split(",")
        survivor, losers = ids[0], ids[1:]
        for loser_id in losers:
            conn.execute("UPDATE observations SET node_id = ? WHERE node_id = ?", (survivor, loser_id))
            try:
                conn.execute("UPDATE edges SET src_node = ? WHERE src_node = ?", (survivor, loser_id))
            except sqlite3.IntegrityError:
                conn.execute("DELETE FROM edges WHERE src_node = ?", (loser_id,))  # survivor already had this exact edge
            try:
                conn.execute("UPDATE edges SET dst_node = ? WHERE dst_node = ?", (survivor, loser_id))
            except sqlite3.IntegrityError:
                conn.execute("DELETE FROM edges WHERE dst_node = ?", (loser_id,))
            conn.execute("DELETE FROM nodes WHERE node_id = ?", (loser_id,))
    if dupes:
        conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('person','project','preference','event','thing','place')),
            label TEXT NOT NULL,
            purpose_scope TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS edges (
            edge_id TEXT PRIMARY KEY,
            src_node TEXT NOT NULL,
            rel TEXT NOT NULL,
            dst_node TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(src_node, rel, dst_node)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            obs_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            fact TEXT NOT NULL,
            source TEXT NOT NULL CHECK(source IN ('user_said','gmail','imessage','calendar','triage','manual')),
            source_ref TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    # UNIQUE(kind, label, purpose_scope) via an index rather than a table
    # constraint — SQLite can't ALTER TABLE to retrofit one onto a table
    # that already exists (this needs to apply to ~/.nala/memory.db as it
    # already exists today, not just fresh databases). Dedupe first, since
    # CREATE UNIQUE INDEX fails outright if any duplicates are already there.
    _dedupe_existing_nodes(conn)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_kind_label_scope ON nodes(kind, label, purpose_scope)")


def new_id() -> str:
    return uuid.uuid4().hex


def upsert_node(kind: str, label: str, purpose_scope: str, data_dir: Path | None = None) -> dict:
    """Atomic find-or-create — mirrors add_edge's INSERT-OR-IGNORE discipline
    rather than the old SELECT-then-INSERT/UPDATE, which had a TOCTOU race
    window: two concurrent callers (serve + scheduler + cli are genuinely
    separate processes) could both see "no existing row" and both insert,
    producing duplicate nodes for the same (kind, label, purpose_scope). The
    UNIQUE index (see ensure_schema) makes the INSERT itself the single
    point of truth — only one caller's row ever lands, and everyone
    (winner or not) re-SELECTs to discover it."""
    if kind not in VALID_KINDS:
        raise MemoryError(f"unknown node kind '{kind}'")
    if not label:
        raise MemoryError("node label is required")
    if not purpose_scope:
        raise MemoryError("node purpose_scope is required")

    conn = connect(data_dir)
    try:
        now = datetime.now(timezone.utc).isoformat()
        node_id = new_id()
        cur = conn.execute(
            "INSERT OR IGNORE INTO nodes (node_id, kind, label, purpose_scope, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (node_id, kind, label, purpose_scope, now, now),
        )
        conn.commit()
        created = cur.rowcount == 1

        if not created:
            # Either it already existed, or we just lost a concurrent race —
            # either way, touch updated_at on whichever row actually won and
            # report its real node_id, never our own discarded candidate.
            conn.execute(
                "UPDATE nodes SET updated_at = ? WHERE kind = ? AND label = ? AND purpose_scope = ?",
                (now, kind, label, purpose_scope),
            )
            conn.commit()
            row = conn.execute(
                "SELECT node_id FROM nodes WHERE kind = ? AND label = ? AND purpose_scope = ?",
                (kind, label, purpose_scope),
            ).fetchone()
            node_id = row["node_id"]

        return {"node_id": node_id, "kind": kind, "label": label, "purpose_scope": purpose_scope, "created": created}
    finally:
        conn.close()


def add_edge(src_node: str, rel: str, dst_node: str, data_dir: Path | None = None) -> dict:
    if not rel:
        raise MemoryError("edge rel is required")

    conn = connect(data_dir)
    try:
        src = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (src_node,)).fetchone()
        dst = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (dst_node,)).fetchone()
        if not src or not dst:
            raise MemoryError("edge references a node_id that doesn't exist")

        now = datetime.now(timezone.utc).isoformat()
        edge_id = new_id()
        conn.execute(
            "INSERT OR IGNORE INTO edges (edge_id, src_node, rel, dst_node, created_at) VALUES (?,?,?,?,?)",
            (edge_id, src_node, rel, dst_node, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM edges WHERE src_node = ? AND rel = ? AND dst_node = ?", (src_node, rel, dst_node)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def add_observation(
    fact: str,
    source: str,
    source_ref: str,
    *,
    node_id: str | None = None,
    kind: str | None = None,
    label: str | None = None,
    purpose_scope: str | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Records a fact against a node. Pass an existing node_id directly, or
    (kind, label, purpose_scope) to find-or-create the node first — the
    common "I learned something about X, possibly a new X" case in one call.

    Provenance is non-negotiable: source and source_ref are both required,
    not optional extras."""
    if not source:
        raise MemoryError("observation must carry a source — provenance is non-negotiable")
    if source not in VALID_SOURCES:
        raise MemoryError(f"unknown source '{source}'")
    if not source_ref:
        raise MemoryError("observation must carry a source_ref — provenance is non-negotiable")
    if not fact:
        raise MemoryError("observation fact is required")

    if node_id is None:
        if not (kind and label and purpose_scope):
            raise MemoryError("add_observation needs either node_id or (kind, label, purpose_scope)")
        node = upsert_node(kind, label, purpose_scope, data_dir)
        node_id = node["node_id"]

    conn = connect(data_dir)
    try:
        node_row = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not node_row:
            raise MemoryError(f"observation references a node_id that doesn't exist: {node_id}")

        now = datetime.now(timezone.utc).isoformat()
        obs_id = new_id()
        conn.execute(
            "INSERT INTO observations (obs_id, node_id, fact, source, source_ref, observed_at, created_at) VALUES (?,?,?,?,?,?,?)",
            (obs_id, node_id, fact, source, source_ref, now, now),
        )
        conn.commit()
        return {"obs_id": obs_id, "node_id": node_id, "fact": fact, "source": source, "source_ref": source_ref, "observed_at": now}
    finally:
        conn.close()


def delete_node(node_id: str, data_dir: Path | None = None) -> dict:
    conn = connect(data_dir)
    try:
        node = conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not node:
            raise MemoryError(f"no such node_id: {node_id}")
        conn.execute("DELETE FROM observations WHERE node_id = ?", (node_id,))
        conn.execute("DELETE FROM edges WHERE src_node = ? OR dst_node = ?", (node_id, node_id))
        conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))
        conn.commit()
        return dict(node)
    finally:
        conn.close()


def query(
    label: str | None = None,
    kind: str | None = None,
    purpose_scope: str | None = None,
    data_dir: Path | None = None,
) -> dict:
    conn = connect(data_dir)
    try:
        clauses = []
        params: list = []
        if label:
            clauses.append("label LIKE ?")
            params.append(f"%{label}%")
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if purpose_scope:
            clauses.append("purpose_scope = ?")
            params.append(purpose_scope)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        nodes = [dict(r) for r in conn.execute(f"SELECT * FROM nodes {where} ORDER BY updated_at DESC", params).fetchall()]

        node_ids = [n["node_id"] for n in nodes]
        edges: list[dict] = []
        observations: list[dict] = []
        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            edges = [dict(r) for r in conn.execute(
                f"SELECT * FROM edges WHERE src_node IN ({placeholders}) OR dst_node IN ({placeholders})",
                node_ids + node_ids,
            ).fetchall()]
            observations = [dict(r) for r in conn.execute(
                f"SELECT * FROM observations WHERE node_id IN ({placeholders}) ORDER BY observed_at DESC",
                node_ids,
            ).fetchall()]

        return {"nodes": nodes, "edges": edges, "observations": observations}
    finally:
        conn.close()
