"""Deterministic safety checks. None of these call a model, so they can't be talked out of working.

- detect_injection: flags attempts to give the agents new instructions (candidate answers,
  coffee-chat notes, pasted press releases).
- mask_pii: removes emails and phone numbers before any text leaves the machine.
- check_claim: a deal claim counts as verified only if its quote is really in the source
  and every number in the claim appears in that quote.
"""

from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(instruction|instructions|rules|prompt|rubric|guidelines)\b",
    r"\bsystem prompt\b",
    r"\byou are now\b",
    r"\b(developer|god|admin) mode\b",
    r"\b(give|award|grade|score|rate|mark)\b[^.\n]{0,30}\b(5|five|10|ten|perfect|full|maximum|max|top)\s*(/\s*5|out of|score|marks|points|rating|stars)",
    r"\b(5|10)\s*/\s*(5|10)\b[^.\n]{0,20}\b(please|now|for this)\b",
    r"\bnote to (ai|llm|the model|assistant|grader)",
    r"\b(reveal|print|show)\b[^.\n]{0,20}\b(your|the)\b[^.\n]{0,15}\b(prompt|instructions|rubric|reference answer)",
    r"\bact as\b[^.\n]{0,30}\b(grader|system|developer|admin)",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def detect_injection(text: str) -> list[str]:
    """Return the suspicious phrases found in text (empty list when clean)."""
    hits = []
    for rx in _INJECTION_RE:
        for m in rx.finditer(text or ""):
            hits.append(m.group(0).strip())
    return hits


def quarantine(text: str) -> tuple[str, list[str]]:
    """Remove sentences that contain injection phrases. Returns (clean_text, removed_sentences).
    Line breaks are kept so quotes from the clean text still match the original wording."""
    removed: list[str] = []
    clean_lines = []
    for line in (text or "").splitlines():
        kept = []
        for sent in re.split(r"(?<=[.!?])\s+", line):
            if sent.strip() and detect_injection(sent):
                removed.append(sent.strip())
            else:
                kept.append(sent)
        clean_lines.append(" ".join(kept))
    return "\n".join(clean_lines), removed


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)")


def mask_pii(text: str) -> str:
    """Replace email addresses and phone numbers with placeholders."""
    text = _EMAIL_RE.sub("[email removed]", text or "")
    return _PHONE_RE.sub("[phone removed]", text)


def clip(text: str, max_chars: int) -> tuple[str, bool]:
    """Cut text to max_chars. Returns (text, was_cut)."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def wrap_untrusted(label: str, text: str) -> str:
    """Put user-supplied text inside clear data tags so the model treats it as data."""
    safe = (text or "").replace("</", "<\\/")
    return f"<{label}>\n{safe}\n</{label}>"


# ---------------------------------------------------------------------------
# Fact checking for deal prep
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def numbers_in(text: str) -> set[str]:
    """Numbers in text, normalized (commas removed, trailing .0 dropped)."""
    out = set()
    for raw in _NUM_RE.findall(text or ""):
        n = raw.replace(",", "")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


def quote_in_source(quote: str, source: str) -> bool:
    q = _norm(quote).strip(" .\"'")
    if len(q) < 8:
        return False
    src = _norm(source)
    # allow quotes that skip words with "..."
    parts = [p.strip() for p in re.split(r"\.\.\.|…", q) if p.strip()]
    return all(p in src for p in parts)


def check_claim(claim: str, quote: str, source: str) -> tuple[bool, str]:
    """Verify one claim against the source text. Returns (verified, reason)."""
    if not quote_in_source(quote, source):
        return False, "Quoted text was not found in the source."
    missing = numbers_in(claim) - numbers_in(quote)
    if missing:
        return False, f"Number(s) {', '.join(sorted(missing))} are not in the quoted source text."
    return True, "Quote found in source; all numbers match."


def unsupported_numbers(text: str, source: str) -> set[str]:
    """Numbers used in generated text that never appear in the source."""
    return numbers_in(text) - numbers_in(source)


def clamp_score(value) -> int:
    try:
        return max(1, min(5, int(round(float(value)))))
    except (TypeError, ValueError):
        return 1
