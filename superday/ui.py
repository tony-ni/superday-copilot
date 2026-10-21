"""Small UI building blocks shared by the pages."""

from __future__ import annotations

from dash import dcc, html

YALE = "#00356b"
YALE_2 = "#286dc0"
YALE_3 = "#63aaff"


def page(title: str, subtitle: str, *children):
    return html.Div([html.H1(title, className="page-title"), html.P(subtitle, className="page-sub"), *children])


def card(title, *children, **kw):
    return html.Div([html.H3(title) if title else None, *children], className="card", **kw)


def kpi(label, value, sub=""):
    return html.Div([html.Div(label, className="kpi-label"), html.Div(value, className="kpi-value"),
                     html.Div(sub, className="kpi-sub")], className="kpi")


def alert(text, level="info"):
    return html.Div(text, className=f"alert alert-{level}")


def badge(text, kind="blue"):
    return html.Span(text, className=f"badge badge-{kind}")


def score_circle(n):
    return html.Span(str(n), className=f"score score-{n}", title=f"Overall {n}/5")


def bullets(items, empty="None"):
    items = [i for i in (items or []) if i]
    if not items:
        return html.Div(empty, className="empty")
    return html.Ul([html.Li(i) for i in items])


def error_box(exc: Exception):
    return alert(f"{exc}", "danger")


def feedback_panel(grade: dict, reference: dict | None = None, show_model=True):
    """Render a Grader result."""
    parts = [
        html.Div([
            score_circle(grade["overall"]),
            html.Div([html.Div("Overall score", className="kpi-label"),
                      html.Div(grade["verdict"], style={"fontWeight": 600})], style={"flex": 1}),
        ], style={"display": "flex", "gap": "14px", "alignItems": "center"}),
        html.Div([html.Div([html.B(f"{grade[k]}/5"), f" {label}"], className="dim")
                  for k, label in (("substance", "Substance"), ("structure", "Structure"), ("delivery", "Delivery"))],
                 className="dim-scores"),
    ]
    if grade.get("injection_attempt"):
        where = ("Blocked by the input scanner before it reached the AI (no tokens spent)"
                 if grade.get("blocked_before_model") else "Flagged by the Grader agent")
        parts.append(alert(f"Safety guard: this answer tried to instruct the grader "
                           f"({'; '.join(grade.get('guard_flags') or ['manipulation attempt'])}). {where}. Score capped at 1.",
                           "danger"))
        parts.append(html.Div([html.H4("What to do"), bullets(grade.get("improvements"))]))
        return html.Div(parts, className="feedback")
    parts += [
        html.Div([html.H4("What worked"), bullets(grade.get("strengths"), "Nothing yet.")]),
        html.Div([html.H4("How to improve"), bullets(grade.get("improvements"))]),
        html.Div([html.H4("Key points you missed"), bullets(grade.get("missed_key_points"), "None: you covered them all.")]),
    ]
    if show_model and grade.get("model_answer"):
        parts.append(html.Div([html.H4("A 5/5 answer sounds like"), html.Div(grade["model_answer"], className="model-answer")]))
    if reference:
        parts.append(html.Details([html.Summary("Reference answer from the question bank"),
                                   html.P(reference["reference_answer"])], style={"marginTop": "12px"}))
    return html.Div(parts, className="feedback")


def loading(child, **kw):
    return dcc.Loading(child, type="dot", color=YALE, **kw)


def fig_layout(fig, height=300):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Segoe UI, system-ui, sans-serif", color="#1d2733", size=13), showlegend=False,
    )
    fig.update_xaxes(gridcolor="#e8eef6", zeroline=False)
    fig.update_yaxes(gridcolor="#e8eef6", zeroline=False)
    return fig
