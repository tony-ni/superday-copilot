"""SQLite storage: trackers, practice attempts, mock sessions, deal analyses and the LLM usage log."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, bank TEXT NOT NULL, grp TEXT, office TEXT,
    deadline TEXT, status TEXT DEFAULT 'Not started', referral TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS coffee_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT, contact TEXT NOT NULL, bank TEXT NOT NULL, grp TEXT,
    title TEXT, chat_date TEXT, notes TEXT, thank_you_sent INTEGER DEFAULT 0, follow_up TEXT);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, source TEXT, session_id INTEGER,
    question_id TEXT, category TEXT, question TEXT, answer TEXT, overall INTEGER,
    feedback_json TEXT, flagged INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS mock_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, bank TEXT, grp TEXT,
    status TEXT, plan_json TEXT, summary_json TEXT, overall REAL, run_id TEXT);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, title TEXT, source TEXT, result_json TEXT, run_id TEXT);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT, agent TEXT, step INTEGER, model TEXT,
    input_tokens INTEGER, cached_tokens INTEGER, cache_write_tokens INTEGER, output_tokens INTEGER,
    reasoning_tokens INTEGER, latency_ms INTEGER, cost_usd REAL, status TEXT);
CREATE TABLE IF NOT EXISTS trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT, agent TEXT, kind TEXT, name TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, participant TEXT, background TEXT, consent INTEGER DEFAULT 0,
    first_task TEXT, hand_start REAL, hand_seconds REAL, app_start REAL, app_seconds REAL, hand_text TEXT, app_text TEXT,
    ratings_json TEXT, quote TEXT, improve TEXT, completed INTEGER DEFAULT 0);
"""


def connect() -> sqlite3.Connection:
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _LOCK, connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple = ()) -> int:
    with _LOCK, connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def init(reset: bool = False) -> None:
    """Create tables. Load the sample profile the first time (or when reset=True)."""
    with _LOCK, connect() as conn:
        if reset:
            for table in ("profile", "applications", "coffee_chats", "attempts", "mock_sessions", "deals"):
                conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(SCHEMA)
        empty = conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 0
        if empty and Path(config.SEED_FILE).is_file():
            _seed(conn, json.loads(Path(config.SEED_FILE).read_text(encoding="utf-8")))
        conn.commit()


def clear_all() -> None:
    """Start from a blank profile (keeps the LLM usage log)."""
    with _LOCK, connect() as conn:
        for table in ("profile", "applications", "coffee_chats", "attempts", "mock_sessions", "deals"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("INSERT INTO profile VALUES ('name', 'New candidate')")
        conn.commit()


def _rel_date(days) -> str | None:
    """Sample data stores dates as offsets from today so the demo never goes stale."""
    if days is None or days == "":
        return None
    return (date.today() + timedelta(days=int(days))).isoformat()


def _seed(conn: sqlite3.Connection, data: dict) -> None:
    for key, value in data.get("profile", {}).items():
        conn.execute("INSERT OR REPLACE INTO profile VALUES (?, ?)", (key, value))
    for a in data.get("applications", []):
        conn.execute(
            "INSERT INTO applications (bank, grp, office, deadline, status, referral, notes) VALUES (?,?,?,?,?,?,?)",
            (a["bank"], a.get("group"), a.get("office"), _rel_date(a.get("deadline_in_days")),
             a.get("status", "Not started"), a.get("referral"), a.get("notes")),
        )
    for c in data.get("coffee_chats", []):
        conn.execute(
            "INSERT INTO coffee_chats (contact, bank, grp, title, chat_date, notes, thank_you_sent, follow_up) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (c["contact"], c["bank"], c.get("group"), c.get("title"), _rel_date(c.get("days_from_today")),
             c.get("notes"), int(c.get("thank_you_sent", 0)), _rel_date(c.get("follow_up_in_days"))),
        )
    for t in data.get("attempts", []):
        conn.execute(
            "INSERT INTO attempts (ts, source, question_id, category, question, answer, overall, feedback_json, flagged) "
            "VALUES (?,?,?,?,?,?,?,?,0)",
            ((datetime.now() + timedelta(days=int(t["days_from_today"]))).isoformat(timespec="seconds"),
             t["source"], t["question_id"], t["category"], t["question"], t.get("answer", ""), t["overall"],
             json.dumps({"note": "sample history"})),
        )


# ---------------------------------------------------------------------------
# Small helpers used by pages and agent tools
# ---------------------------------------------------------------------------
def profile() -> dict:
    return {r["key"]: r["value"] for r in query("SELECT key, value FROM profile")}


def set_profile(key: str, value: str) -> None:
    execute("INSERT OR REPLACE INTO profile VALUES (?, ?)", (key, value))


def applications() -> list[dict]:
    return query("SELECT * FROM applications ORDER BY deadline IS NULL, deadline")


def coffee_chats(bank: str | None = None) -> list[dict]:
    if bank:
        return query("SELECT * FROM coffee_chats WHERE lower(bank) = lower(?) ORDER BY chat_date DESC", (bank,))
    return query("SELECT * FROM coffee_chats ORDER BY chat_date DESC")


def score_summary() -> list[dict]:
    """Average score and attempt count per category (latest 5 attempts per category)."""
    rows = query("SELECT category, overall, ts FROM attempts WHERE overall IS NOT NULL ORDER BY ts DESC")
    by_cat: dict[str, list[int]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], [])
        if len(by_cat[r["category"]]) < 5:
            by_cat[r["category"]].append(r["overall"])
    return sorted(
        ({"category": c, "avg_score": round(sum(v) / len(v), 2), "attempts": len(v)} for c, v in by_cat.items()),
        key=lambda d: d["avg_score"],
    )


def log_trace(run_id: str, agent: str, kind: str, name: str, content) -> None:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)
    execute(
        "INSERT INTO trace_events (ts, run_id, agent, kind, name, content) VALUES (?,?,?,?,?,?)",
        (now(), run_id, agent, kind, name, content[:20_000]),
    )


def spend_today() -> float:
    row = query("SELECT COALESCE(SUM(cost_usd), 0) AS s FROM llm_calls WHERE substr(ts, 1, 10) = ?",
                (date.today().isoformat(),))
    return float(row[0]["s"])
