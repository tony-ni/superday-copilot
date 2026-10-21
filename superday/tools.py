"""Python tools the agents can call. They only read data: no agent can change the trackers,
send email or submit an application (the user does those in the UI)."""

from __future__ import annotations

import json
import random
from datetime import date
from functools import lru_cache

from . import config, db
from .safety import mask_pii, quarantine


@lru_cache(maxsize=1)
def question_bank() -> list[dict]:
    return json.loads(config.QUESTION_BANK_FILE.read_text(encoding="utf-8"))


def question_by_id(qid: str) -> dict | None:
    return next((q for q in question_bank() if q["id"] == qid), None)


CATEGORIES = sorted({q["category"] for q in question_bank()})


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def get_applications() -> dict:
    """All tracked applications with days until each deadline."""
    today = date.today()
    rows = []
    for a in db.applications():
        days = (date.fromisoformat(a["deadline"]) - today).days if a["deadline"] else None
        rows.append({"bank": a["bank"], "group": a["grp"], "status": a["status"], "deadline": a["deadline"],
                     "days_left": days, "referral": a["referral"] or ""})
    return {"today": today.isoformat(), "applications": rows}


def get_coffee_chats(bank: str) -> dict:
    """Coffee-chat notes, optionally for one bank ('' = all). Emails and phone numbers are removed."""
    today = date.today()
    rows = []
    for c in db.coffee_chats(bank or None):
        days = (date.fromisoformat(c["chat_date"]) - today).days if c["chat_date"] else None
        rows.append({"contact": c["contact"], "bank": c["bank"], "group": c["grp"], "title": c["title"],
                     "date": c["chat_date"], "days_from_today": days,
                     "thank_you_sent": bool(c["thank_you_sent"]), "notes": quarantine(mask_pii(c["notes"] or ""))[0]})
    return {"today": today.isoformat(), "coffee_chats": rows}


def get_score_history() -> dict:
    """Average of the latest practice scores (1-5) per topic, weakest first, plus untouched topics."""
    summary = db.score_summary()
    practiced = {s["category"] for s in summary}
    return {"by_category": summary, "never_practiced": [c for c in CATEGORIES if c not in practiced]}


def list_questions(category: str, max_difficulty: int) -> dict:
    """Question ids and text from the bank for one category ('' = all)."""
    qs = [q for q in question_bank()
          if (not category or q["category"].lower() == category.lower()) and q["difficulty"] <= max_difficulty]
    return {"questions": [{"id": q["id"], "category": q["category"], "difficulty": q["difficulty"],
                           "question": q["question"]} for q in qs]}


def pick_practice_question(category: str, exclude_ids: list[str] | None = None) -> dict:
    """Pick a question for drills. category 'Weakest topic' uses the score history."""
    if category == "Weakest topic":
        summary = get_score_history()
        pool_cats = summary["never_practiced"][:1] or [s["category"] for s in summary["by_category"][:2]]
        pool = [q for q in question_bank() if q["category"] in pool_cats]
    else:
        pool = [q for q in question_bank() if not category or q["category"] == category]
    fresh = [q for q in pool if q["id"] not in (exclude_ids or [])] or pool
    return random.choice(fresh)


# ---------------------------------------------------------------------------
# Tool specs (JSON schema the model sees)
# ---------------------------------------------------------------------------
from .llm import INT, STR, tool_spec  # noqa: E402

SPEC_GET_APPLICATIONS = tool_spec("get_applications", "List the candidate's tracked applications with deadlines and status.")
SPEC_GET_COFFEE_CHATS = tool_spec(
    "get_coffee_chats", "Read the candidate's coffee-chat notes. Pass a bank name, or an empty string for all banks.",
    bank=STR)
SPEC_GET_SCORE_HISTORY = tool_spec(
    "get_score_history", "Get the candidate's average practice score (1-5) per topic, weakest first.")
SPEC_LIST_QUESTIONS = tool_spec(
    "list_questions", "List question ids from the interview question bank. category may be '' for all; "
    f"categories: {', '.join(CATEGORIES)}. max_difficulty is 1-3.", category=STR, max_difficulty=INT)
