"""Small UI building blocks shared by the pages."""

from __future__ import annotations

from dash import dcc, html

YALE = "#00356b"
YALE_2 = "#286dc0"
YALE_3 = "#63aaff"


def icon(name: str, cls: str = ""):
    """Line icon drawn with a CSS mask (see .ico-* in style.css); inherits the text color."""
    return html.Span(className=f"ico ico-{name} {cls}".strip(), **{"aria-hidden": "true"})


class _PageIcon(str):
    """Marker passed positionally to page() to choose the header icon."""


def page_icon(name: str) -> _PageIcon:
    return _PageIcon(name)


def page(title: str, subtitle: str, *children, icon_name: str | None = None):
    for c in children:
        if isinstance(c, _PageIcon):
            icon_name = str(c)
    children = tuple(c for c in children if not isinstance(c, _PageIcon))
    head = html.Div([
        html.Div(icon(icon_name), className="page-icon") if icon_name else None,
        html.Div([html.H1(title, className="page-title"), html.P(subtitle, className="page-sub")]),
    ], className="page-head")
    return html.Div([head, *children], className="page-enter")


def card(title, *children, **kw):
    cls = kw.pop("className", "")
    # `is not None`: an empty Dash component (e.g. a Span filled later by a callback) is falsy but must still render.
    return html.Div([html.H3(title) if title is not None else None, *children], className=f"card {cls}".strip(), **kw)


def kpi(label, value, sub="", icon_name=None):
    return html.Div([
        html.Div([icon(icon_name) if icon_name else None, html.Span(label)], className="kpi-label"),
        html.Div(value, className="kpi-value"), html.Div(sub, className="kpi-sub")], className="kpi")


def alert(text, level="info"):
    return html.Div(text, className=f"alert alert-{level}", role="status")


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


def empty_state(icon_name: str, title: str, text: str, action=None):
    return html.Div([html.Div(icon(icon_name), className="empty-icon"), html.Div(title, className="empty-title"),
                     html.Div(text, className="empty-text"), action], className="empty-state")


def kbd(text):
    return html.Kbd(text, className="kbd")


def voice_controls(prefix: str, target: str):
    """Mic button + live status line. Behavior lives in assets/voice.js."""
    return html.Div([
        html.Button("🎤 Answer by voice", id=f"{prefix}-mic", className="btn btn-voice", type="button",
                    title="Speak your answer; it is transcribed into the box below",
                    **{"data-voice-target": target, "data-voice-prefix": prefix}),
        html.Span(id=f"{prefix}-voice-status", className="voice-status", **{"aria-live": "polite"}),
    ], className="voice-bar")


VOICE_NOTE = ("Voice uses your browser's speech recognition (Chrome or Edge). The browser's speech service turns your "
              "audio into text; Superday Copilot never records or stores audio.")


def delivery_strip(stats: dict | None):
    if not stats:
        return None
    lo, hi = stats["target"]
    m, s = divmod(stats["seconds"], 60)
    length_kind = {"on target": "ok", "short": "warn", "long": "warn"}[stats["length"]]
    pace_kind = {"steady": "ok", "slow": "warn", "fast": "warn"}[stats["pace"]]
    filler_kind = "ok" if stats["fillers"] <= 2 else "warn"
    return html.Div([
        html.Div([icon("mic"), " Spoken delivery"], className="delivery-title"),
        html.Div([
            html.Div([html.B(f"{m}:{s:02d}"), html.Span(f"target {lo}–{hi}s"), badge(stats["length"], length_kind)], className="dstat"),
            html.Div([html.B(f"{stats['wpm']} wpm"), html.Span("pace"), badge(stats["pace"], pace_kind)], className="dstat"),
            html.Div([html.B(str(stats["fillers"])), html.Span("filler words" + (f": {', '.join(stats['filler_words'])}" if stats["filler_words"] else "")),
                      badge("clean" if stats["fillers"] <= 2 else "reduce", filler_kind)], className="dstat"),
            html.Div([html.B(str(stats["words"])), html.Span("words")], className="dstat"),
        ], className="dstats"),
    ], className="delivery")


def feedback_panel(grade: dict, reference: dict | None = None, show_model=True):
    """Render a Grader result."""
    parts = [
        html.Div([
            score_circle(grade["overall"]),
            html.Div([html.Div("Overall score", className="kpi-label"),
                      html.Div(grade["verdict"], className="verdict")], style={"flex": 1}),
        ], className="score-head"),
        html.Div([html.Div([html.B(f"{grade[k]}/5"), f" {label}"], className=f"dim dim-{grade[k]}")
                  for k, label in (("substance", "Substance"), ("structure", "Structure"), ("delivery", "Delivery"))],
                 className="dim-scores"),
        delivery_strip(grade.get("delivery_stats")),
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
        html.Div([
            html.Div([html.H4([icon("check"), " What worked"]), bullets(grade.get("strengths"), "Nothing yet.")], className="fb-col fb-good"),
            html.Div([html.H4([icon("arrow-up"), " How to improve"]), bullets(grade.get("improvements"))], className="fb-col fb-fix"),
        ], className="fb-grid"),
        html.Div([html.H4("Key points you missed"), bullets(grade.get("missed_key_points"), "None: you covered them all.")]),
    ]
    if show_model and grade.get("model_answer"):
        parts.append(html.Div([html.H4("A 5/5 answer sounds like"), html.Div(grade["model_answer"], className="model-answer")]))
    if reference:
        parts.append(html.Details([html.Summary("Reference answer from the question bank"),
                                   html.P(reference["reference_answer"])], style={"marginTop": "12px"}))
    return html.Div(parts, className="feedback")


def loading(child, text: str | None = None, **kw):
    """Spinner with a plain-language message about what the agent is doing."""
    spinner = html.Div([html.Div(className="spinner"), html.Div(text or "Working…", className="spinner-text")],
                       className="spinner-wrap")
    return dcc.Loading(child, custom_spinner=spinner, delay_show=150, overlay_style={"visibility": "visible", "opacity": .35},
                       **kw)


def fig_layout(fig, height=300):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Segoe UI, system-ui, sans-serif", color="#1d2733", size=13), showlegend=False,
    )
    fig.update_xaxes(gridcolor="#e8eef6", zeroline=False)
    fig.update_yaxes(gridcolor="#e8eef6", zeroline=False)
    return fig
