"""Settings, .env lookup and model prices for Superday Copilot.

The .env lookup follows the course rule: first the repo folder, then the
folder one level above it. Values already in the process environment win.
Secrets are never printed.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:]
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env() -> list[Path]:
    """Load .env from the repo folder, then the parent folder. Returns the files used."""
    used = []
    for folder in (REPO_DIR, REPO_DIR.parent):
        env_file = folder / ".env"
        if env_file.is_file():
            for key, value in _parse_env_file(env_file).items():
                if value and not os.environ.get(key):
                    os.environ[key] = value
            used.append(env_file)
    return used


ENV_FILES = load_env()

# The course key (PORTKEY_API_KEY) may only be used with gpt-6-luna.
MODEL = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
REASONING_EFFORT = os.getenv("SUPERDAY_REASONING_EFFORT", "low")

# USD per 1M tokens, standard tier (< 272K input tokens). Source: OpenAI API
# pricing for GPT-6 Luna as reported by eesel.ai / anotherwrapper.com (Oct 2026).
PRICE_PER_M = {
    "input": 0.10,
    "cached_input": 0.01,
    "cache_write": 0.125,
    "output": 0.50,
}

# Safety budgets (overspending and loop guards).
MAX_TOOL_STEPS = 6                 # model turns per agent run before the loop guard stops it
RUN_TOKEN_BUDGET = 60_000          # input + output tokens allowed for one agent run
DAILY_SPEND_CAP_USD = float(os.getenv("SUPERDAY_DAILY_CAP_USD", "1.00"))
MAX_ANSWER_CHARS = 4_000           # candidate answers longer than this are cut
MAX_SOURCE_CHARS = 12_000          # pasted press releases longer than this are cut

DB_PATH = Path(os.getenv("SUPERDAY_DB", str(DATA_DIR / "superday.db")))
SEED_FILE = Path(os.getenv("SUPERDAY_SEED", str(DATA_DIR / "sample_profile.json")))
QUESTION_BANK_FILE = DATA_DIR / "question_bank.json"


def provider() -> tuple[str, str] | None:
    """Return (provider_name, api_key) or None when no key is configured."""
    if os.environ.get("PORTKEY_API_KEY"):
        return "portkey", os.environ["PORTKEY_API_KEY"]
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"]
    return None
