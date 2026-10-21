"""Technicals drills, graded against the reference-answer bank."""

from dash import html

from .. import tools
from ..ui import card, page
from . import practice

TECH_CATS = ["Weakest topic"] + [c for c in tools.CATEGORIES if c != "Behavioral"]
practice.register("tech", "technicals")


def layout():
    counts = {c: sum(q["category"] == c for q in tools.question_bank()) for c in TECH_CATS[1:]}
    return page(
        "Technicals",
        "Drill accounting, EV, valuation, DCF, LBO and M&A questions. Every answer is graded against a reference answer, "
        "not the model's memory.",
        html.Div([
            practice.block("tech", TECH_CATS, "Practice a question", "Weakest topic"),
            html.Div([
                card("Question bank", html.Ul([html.Li(f"{c}: {n} questions") for c, n in counts.items()]),
                     html.Div("'Weakest topic' picks from topics you've never practiced or score lowest on.", className="hint")),
                card("Recent attempts", practice.history_table("technicals")),
            ]),
        ], className="grid grid-5-7", style={"gridTemplateColumns": "7fr 5fr"}),
    )
