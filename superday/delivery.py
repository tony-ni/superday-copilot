"""Delivery stats for spoken answers, computed in code (no model call).

The browser's speech recognition gives us the transcript; the browser timer gives us the speaking time.
From those we measure length vs. the target for the question type, pace (words per minute) and filler words.
Note: speech recognizers often drop "um"/"uh", so the filler count is a floor, not an exact count.
"""

from __future__ import annotations

import re

FILLER_RE = re.compile(r"\b(um+|uh+|erm|ah+|hmm+|you know|i mean|kind of|sort of|basically|literally)\b", re.IGNORECASE)

# Rough interview conventions: technicals 30-60 s; resume walks, "why us" and pitches 60-120 s.
LONG_FORM = {"BEH-1", "BEH-2", "BEH-3", "BEH-4", "BEH-5", "BEH-6", "BEH-8", "BEH-9", "MKT-2", "MKT-3"}


def target_seconds(question_id: str) -> tuple[int, int]:
    return (60, 120) if question_id in LONG_FORM else (30, 60)


def delivery_stats(answer: str, voice: dict | None, question_id: str) -> dict | None:
    """Return stats when the answer was spoken (voice store has seconds), else None."""
    if not voice or not voice.get("seconds") or voice["seconds"] < 2:
        return None
    seconds = int(voice["seconds"])
    words = len((answer or "").split())
    wpm = round(words / (seconds / 60)) if seconds else 0
    fillers = [m.group(0).lower() for m in FILLER_RE.finditer(answer or "")]
    lo, hi = target_seconds(question_id)
    length = "short" if seconds < lo * 0.7 else "long" if seconds > hi * 1.15 else "on target"
    pace = "slow" if wpm < 110 else "fast" if wpm > 175 else "steady"
    return {"seconds": seconds, "words": words, "wpm": wpm, "fillers": len(fillers),
            "filler_words": sorted(set(fillers)), "target": [lo, hi], "length": length, "pace": pace}


def for_grader(stats: dict | None) -> str:
    """One line the Grader can use when scoring delivery."""
    if not stats:
        return "Answer was typed (no spoken timing available)."
    fw = f" ({', '.join(stats['filler_words'])})" if stats["filler_words"] else ""
    return (f"Answer was spoken. Measured by the app: {stats['seconds']} s (target {stats['target'][0]}-"
            f"{stats['target'][1]} s), {stats['wpm']} words per minute, {stats['fillers']} filler word(s){fw}. "
            "The text is a speech-to-text transcript, so ignore missing punctuation and obvious transcription errors.")
