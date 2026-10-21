"""Technicals drills, graded against the reference-answer bank. Answer by typing or by voice."""

from dash import html

from .. import db, tools
from ..ui import card, icon, kbd, page
from . import practice

TECH_CATS = ["Weakest topic"] + [c for c in tools.CATEGORIES if c != "Behavioral"]
practice.register("tech", "technicals")


def _mastery():
    """Average of the latest scores per topic, as bars (code, no AI)."""
    scores = {s["category"]: s for s in db.score_summary()}
    rows = []
    for c in TECH_CATS[1:]:
        n_q = sum(q["category"] == c for q in tools.question_bank())
        s = scores.get(c)
        avg = s["avg_score"] if s else None
        level = "none" if avg is None else "good" if avg >= 4 else "mid" if avg >= 3 else "low"
        rows.append(html.Div([
            html.Div([html.Span(c, className="m-name"),
                      html.Span(f"{avg:.1f}/5" if avg is not None else "not practiced", className=f"m-score m-{level}")],
                     className="m-head"),
            html.Div(html.Div(className=f"m-fill m-{level}", style={"width": f"{(avg or 0) * 20:.0f}%"}), className="m-track"),
            html.Div(f"{n_q} questions in the bank" + (f" · {s['attempts']} recent attempt(s)" if s else ""), className="m-sub"),
        ], className="m-row"))
    return rows


def layout():
    return page(
        "Technicals",
        "Drill accounting, EV, valuation, DCF, LBO and M&A out loud, like a real interview. Every answer is graded "
        "against a reference answer, not the model's memory.",
        html.Div([
            practice.block("tech", TECH_CATS, "Practice a question", "Weakest topic"),
            html.Div([
                card("Topic mastery", *_mastery(),
                     html.Div("'Weakest topic' picks from topics you haven't practiced or score lowest on.", className="hint")),
                card("Practice like the real thing",
                     html.Ul([
                         html.Li([icon("volume"), " Click ", html.B("Read aloud"), " to hear the question."]),
                         html.Li([icon("mic"), " Click ", html.B("Answer by voice"), " and talk. Your words appear live; click Stop when done."]),
                         html.Li([icon("check"), " Fix any misheard terms, then grade (", kbd("Ctrl"), " + ", kbd("Enter"), ")."]),
                         html.Li([icon("clock"), " Spoken answers also get timing, pace and filler-word feedback."]),
                     ], className="howto")),
                card("Recent attempts", practice.history_table("technicals")),
            ]),
        ], className="grid grid-7-5"),
        icon_name="calc",
    )
