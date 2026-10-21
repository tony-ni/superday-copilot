"""User Test: a timed, before/after test you can run with classmates on your laptop.

Each participant does the same task twice: prepare for tomorrow's coffee chat (a 30-second intro and three
questions to ask) once by hand and once with Superday Copilot. The app records the times itself. The order
alternates between participants (P1 by hand first, P2 with the app first, ...) so practice effects cancel out
on average. A short survey follows. Results stay in the local database (never pushed to GitHub); the report
shows only anonymous P-numbers, and quotes only from participants who agreed.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
import time

from dash import Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update

from .. import agents, config, db, llm
from ..ui import alert, badge, card, empty_state, error_box, icon, loading, page, page_icon

SAMPLE = json.loads((config.DATA_DIR / "sample_profile.json").read_text(encoding="utf-8"))
SCENARIO_CHAT = next(c for c in SAMPLE["coffee_chats"] if c["contact"] == "Jordan Lee")
CHAT = {"contact": SCENARIO_CHAT["contact"], "bank": SCENARIO_CHAT["bank"], "grp": SCENARIO_CHAT["group"],
        "title": SCENARIO_CHAT["title"], "notes": SCENARIO_CHAT["notes"]}
TASK = (f"Your coffee chat with {CHAT['contact']} ({CHAT['title']}, {CHAT['bank']} {CHAT['grp']}) is tomorrow. "
        "Prepare (1) a 30-second intro about yourself and (2) three good questions to ask. "
        "Finish when you would be comfortable using it in the real chat.")
BACKGROUNDS = ["First-year MBA, recruiting for IB", "First-year MBA, other finance recruiting",
               "Second-year MBA with IB offer or experience", "Other"]
RATING = [{"label": f" {i}", "value": i} for i in range(1, 6)]
HAND_TEMPLATE = "30-second intro:\n\n\nQuestions to ask:\n1.\n2.\n3."


def _sample_loaded() -> bool:
    return db.profile().get("name") == SAMPLE["profile"]["name"]


def _scenario():
    other = [c for c in SAMPLE["coffee_chats"] if c["bank"] == CHAT["bank"] and c["contact"] != CHAT["contact"]]
    return card([icon("user"), "The scenario (same for every participant)"],
                html.P(TASK, className="study-task"),
                html.Div([
                    html.Div([html.H4("You are: Alex Chen"), html.Div(SAMPLE["profile"]["background"], className="hint"),
                              html.Pre(SAMPLE["profile"]["resume"], className="study-pre")]),
                    html.Div([html.H4(f"Your notes on {CHAT['contact']}"), html.P(CHAT["notes"]),
                              *([html.H4(f"Other notes on {CHAT['bank']}"), *[html.P(c["notes"]) for c in other]] if other else [])]),
                ], className="grid grid-2"),
                className="study-scenario")


def layout():

    setup = card(
        "Run a 15-minute user test with a classmate",
        html.Ol([
            html.Li("Your classmate prepares for a coffee chat twice: once by hand, once with the app. The app times both."),
            html.Li("The order alternates between participants so practice effects cancel out."),
            html.Li("They answer a 1-minute survey. Results stay on this laptop; the report shows only P1, P2, … and "
                    "quotes only from people who agree."),
        ], className="study-steps"),
        alert("This test uses the fictional sample candidate. Go to Usage & Safety → Reset sample data first.", "warning")
        if not _sample_loaded() else None,
        html.Div([
            html.Div([html.Label("Name or initials (stays on this laptop)", className="field"),
                      dcc.Input(id="st-name", type="text", placeholder="optional")]),
            html.Div([html.Label("Background", className="field"),
                      dcc.Dropdown(BACKGROUNDS, BACKGROUNDS[0], id="st-bg", clearable=False)]),
        ], className="grid grid-2"),
        dcc.Checklist([{"label": " I agree that my anonymous ratings and comments may be quoted in the project report.",
                        "value": "yes"}], [], id="st-consent", style={"marginTop": "12px"}),
        html.Div([html.Button([icon("play"), " Start next participant"], id="st-begin", className="btn btn-lg",
                              disabled=not _sample_loaded())], className="btn-row"),
        id="st-setup",
    )

    def task_panel(kind):
        is_hand = kind == "hand"
        return card(
            html.Span(id=f"st-{kind}-title"),
            html.P("Write it yourself, without the app. Use the scenario below." if is_hand else
                   "Click Start: the app drafts your prep. Edit it until you'd actually use it, then click Done.",
                   className="hint"),
            html.Div([
                html.Button([icon("play"), " Start timer" if is_hand else " Start and generate with the app"],
                            id=f"st-{kind}-start", className="btn"),
                html.Span(id=f"st-{kind}-clock", className="study-clock"),
            ], className="btn-row", style={"marginTop": 0}),
            loading(html.Div(dcc.Textarea(id=f"st-{kind}-text", className="answer-box study-text",
                                          value=HAND_TEMPLATE if is_hand else "",
                                          placeholder="" if is_hand else "The app's draft appears here after you click Start.")),
                    "Superday Copilot is preparing the draft…"),
            html.Div([html.Button([icon("check"), " I'm done"], id=f"st-{kind}-done", className="btn btn-secondary")],
                     className="btn-row"),
            id=f"st-p-{kind}", style={"display": "none"},
        )

    survey = card(
        "Last step: 1-minute survey",
        html.Div([
            _rate("st-q-hand", "How good was your by-hand prep? (1 = weak, 5 = interview-ready)"),
            _rate("st-q-app", "How good was the app-assisted prep?"),
            _rate("st-q-useful", "How useful would Superday Copilot be for your own recruiting?"),
            _rate("st-q-ease", "How easy was it to use?"),
        ], className="grid grid-2"),
        html.Label("Would you use it during recruiting season?", className="field"),
        dcc.RadioItems(["Yes, weekly", "Maybe, occasionally", "No"], None, id="st-q-use", inline=True, className="study-radio"),
        html.Label("In a sentence or two, what did you think?", className="field"),
        dcc.Textarea(id="st-quote", style={"minHeight": "70px"}),
        html.Label("What would make it more useful?", className="field"),
        dcc.Textarea(id="st-improve", style={"minHeight": "60px"}),
        html.Div([html.Button([icon("send"), " Submit"], id="st-submit", className="btn")], className="btn-row"),
        id="st-p-survey", style={"display": "none"},
    )

    return page(
        "User Test",
        "Collect real before/after evidence: time to prepare for a coffee chat by hand vs. with the app, plus ratings.",
        page_icon("user"),
        dcc.Store(id="st-state", storage_type="session"),
        dcc.Interval(id="st-tick", interval=1000),
        html.Div(id="st-msg"),
        setup,
        html.Div([task_panel("hand"), task_panel("app")], className="study-tasks"),
        survey,
        html.Div(id="st-scenario-wrap", children=_scenario(), style={"display": "none"}),
        card([icon("chart"), "Results so far"], html.Div(id="st-results", children=results_view()),
             html.Div([html.Button("Download CSV", id="st-csv-btn", className="btn btn-secondary"), dcc.Download(id="st-csv"),
                       dcc.Dropdown(id="st-del-pick", placeholder="Delete a session…", style={"minWidth": "220px"},
                                    options=_session_options()),
                       html.Button("Delete", id="st-del", className="btn btn-danger")], className="btn-row")),
    )


def _rate(cid, label):
    return html.Div([html.Label(label, className="field"),
                     dcc.RadioItems(RATING, None, id=cid, inline=True, className="study-radio")])


def _session_options():
    return [{"label": f"P{i + 1} · {r['ts'][:16].replace('T', ' ')}{'' if r['completed'] else ' (incomplete)'}", "value": r["id"]}
            for i, r in enumerate(db.query("SELECT id, ts, completed FROM study_sessions ORDER BY id"))]


RESET_OUTPUTS = [Output("st-name", "value"), Output("st-consent", "value"), Output("st-q-hand", "value"),
                 Output("st-q-app", "value"), Output("st-q-useful", "value"), Output("st-q-ease", "value"),
                 Output("st-q-use", "value"), Output("st-quote", "value"), Output("st-improve", "value")]
RESET_VALUES = ("", [], None, None, None, None, None, "", "")

# ---------------------------------------------------------------------------
# Flow: setup -> task 1 -> task 2 -> survey -> done
# ---------------------------------------------------------------------------
@callback(
    Output("st-state", "data"), Output("st-msg", "children"),
    Output("st-hand-text", "value", allow_duplicate=True), Output("st-app-text", "value", allow_duplicate=True),
    *RESET_OUTPUTS,
    Input("st-begin", "n_clicks"), Input("st-hand-start", "n_clicks"), Input("st-hand-done", "n_clicks"),
    Input("st-app-done", "n_clicks"), Input("st-submit", "n_clicks"),
    State("st-name", "value"), State("st-bg", "value"), State("st-consent", "value"), State("st-state", "data"),
    State("st-hand-text", "value"), State("st-app-text", "value"),
    State("st-q-hand", "value"), State("st-q-app", "value"), State("st-q-useful", "value"), State("st-q-ease", "value"),
    State("st-q-use", "value"), State("st-quote", "value"), State("st-improve", "value"),
    prevent_initial_call=True,
)
def flow(*args):
    out = _flow(*args)
    # After a successful submit, clear everything the next participant must fill in themselves (including consent).
    done = ctx.triggered_id == "st-submit" and out[0] is None
    return (*out, *(RESET_VALUES if done else (no_update,) * len(RESET_VALUES)))


def _flow(_b, _hs, _hd, _ad, _sub, name, bg, consent, st, hand_text, app_text, q_hand, q_app, q_useful, q_ease, q_use,
          quote, improve):
    trig = ctx.triggered_id
    now = time.time()
    if trig == "st-begin":
        n = len(db.query("SELECT id FROM study_sessions"))
        first = "hand" if n % 2 == 0 else "app"
        sid = db.execute("INSERT INTO study_sessions (ts, participant, background, consent, first_task) VALUES (?,?,?,?,?)",
                         (db.now(), (name or "").strip(), bg, int("yes" in (consent or [])), first))
        order = [first, "app" if first == "hand" else "hand"]
        return {"sid": sid, "order": order, "step": 0, "start": {}}, None, HAND_TEMPLATE, ""
    if not st:
        return no_update, alert("Start a participant first.", "warning"), no_update, no_update
    if trig == "st-hand-start":
        st["start"]["hand"] = now
        db.execute("UPDATE study_sessions SET hand_start = ? WHERE id = ?", (now, st["sid"]))
        return st, None, no_update, no_update
    if trig in ("st-hand-done", "st-app-done"):
        kind = "hand" if trig == "st-hand-done" else "app"
        if kind not in st["start"]:
            return no_update, alert("Click Start first, so the time is measured.", "warning"), no_update, no_update
        text = hand_text if kind == "hand" else app_text
        if not (text or "").strip() or (kind == "hand" and text.strip() == HAND_TEMPLATE.strip()):
            return no_update, alert("Write the intro and questions before clicking Done.", "warning"), no_update, no_update
        secs = round(now - st["start"][kind], 1)
        db.execute(f"UPDATE study_sessions SET {kind}_seconds = ?, {kind}_text = ? WHERE id = ?", (secs, text, st["sid"]))
        st["step"] += 1
        return st, alert(f"Saved: {_fmt(secs)}.", "ok"), no_update, no_update
    if trig == "st-submit":
        if None in (q_hand, q_app, q_useful, q_ease) or not q_use:
            return no_update, alert("Please answer all the rating questions.", "warning"), no_update, no_update
        ratings = {"hand_quality": q_hand, "app_quality": q_app, "useful": q_useful, "ease": q_ease, "would_use": q_use}
        db.execute("UPDATE study_sessions SET ratings_json = ?, quote = ?, improve = ?, completed = 1 WHERE id = ?",
                   (json.dumps(ratings), (quote or "").strip(), (improve or "").strip(), st["sid"]))
        return None, alert("Thank you! Results saved. Start the next participant when ready.", "ok"), HAND_TEMPLATE, ""
    return no_update, no_update, no_update, no_update


@callback(
    Output("st-app-text", "value"), Output("st-state", "data", allow_duplicate=True), Output("st-msg", "children", allow_duplicate=True),
    Input("st-app-start", "n_clicks"), State("st-state", "data"), prevent_initial_call=True,
    running=[(Output("st-app-start", "disabled"), True, False)],
)
def app_start(_, st):
    if not st:
        return no_update, no_update, alert("Start a participant first.", "warning")
    started = time.time()  # the clock starts at the click, so AI waiting time counts against the app
    st["start"]["app"] = started
    db.execute("UPDATE study_sessions SET app_start = ? WHERE id = ?", (started, st["sid"]))
    try:
        out = agents.coffee_chat_prep(CHAT, llm.new_run_id("study"))
    except llm.AIError as exc:
        return "", st, error_box(exc)
    qs = "\n".join(f"{i}. {q}" for i, q in enumerate(out["questions_to_ask"], 1))
    draft = (f"30-second intro:\n{out['intro_30s']}\n\nQuestions to ask:\n{qs}\n\n"
             f"(Edit this until you'd use it: trim to your best 3 questions.)")
    return draft, st, None


@callback(
    Output("st-setup", "style"), Output("st-p-hand", "style"), Output("st-p-app", "style"), Output("st-p-survey", "style"),
    Output("st-scenario-wrap", "style"), Output("st-hand-title", "children"), Output("st-app-title", "children"),
    Output("st-results", "children"), Output("st-del-pick", "options"),
    Input("st-state", "data"),
)
def render(st):
    hide, show = {"display": "none"}, {}
    results = results_view()
    if not st:
        return show, hide, hide, hide, hide, "", "", results, _session_options()
    step, order = st["step"], st["order"]
    current = order[step] if step < 2 else None
    titles = {k: f"Task {order.index(k) + 1} of 2 · {'By hand' if k == 'hand' else 'With Superday Copilot'}" for k in order}
    return (hide, show if current == "hand" else hide, show if current == "app" else hide,
            show if step >= 2 else hide, show if current else hide,
            [icon("calc" if order[0] == "hand" else "spark"), " ", titles["hand"]],
            [icon("spark"), " ", titles["app"]], results, _session_options())


clientside_callback(
    """function(n, st) {
        const fmt = s => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
        const out = ['', ''];
        if (!st || !st.start) return out;
        ['hand', 'app'].forEach((k, i) => {
            const t0 = st.start[k];
            const active = st.order && st.order[st.step] === k;
            if (t0 && active) out[i] = '⏱ ' + fmt(Date.now() / 1000 - t0);
        });
        return out;
    }""",
    Output("st-hand-clock", "children"), Output("st-app-clock", "children"),
    Input("st-tick", "n_intervals"), State("st-state", "data"),
)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
def _fmt(secs):
    if secs is None:
        return "-"
    m, s = divmod(int(round(secs)), 60)
    return f"{m}:{s:02d}"


def completed_sessions() -> list[dict]:
    rows = db.query("SELECT * FROM study_sessions WHERE completed = 1 ORDER BY id")
    for i, r in enumerate(rows, 1):
        r["label"] = f"P{i}"
        r["ratings"] = json.loads(r["ratings_json"] or "{}")
    return rows


def summary(rows: list[dict]) -> dict | None:
    pairs = [(r["hand_seconds"], r["app_seconds"]) for r in rows if r["hand_seconds"] and r["app_seconds"]]
    if not pairs:
        return None
    hand = statistics.median(p[0] for p in pairs)
    app = statistics.median(p[1] for p in pairs)
    saved = statistics.median(1 - a / h for h, a in pairs)
    avg = lambda key: round(statistics.mean(r["ratings"][key] for r in rows), 1)  # noqa: E731
    return {"n": len(pairs), "hand": hand, "app": app, "saved": saved, "hand_q": avg("hand_quality"),
            "app_q": avg("app_quality"), "useful": avg("useful"), "ease": avg("ease"),
            "would_use": sum(r["ratings"]["would_use"].startswith("Yes") for r in rows)}


def results_view():
    rows = completed_sessions()
    if not rows:
        return empty_state("chart", "No completed sessions yet",
                           "Run the test with 2–3 classmates. Results and a summary will appear here.")
    s = summary(rows)
    head = html.Div([
        html.Div([html.B(f"{s['n']}"), html.Span("participants")], className="dstat"),
        html.Div([html.B(_fmt(s["hand"])), html.Span("median by hand")], className="dstat"),
        html.Div([html.B(_fmt(s["app"])), html.Span("median with app")], className="dstat"),
        html.Div([html.B(f"{s['saved']:.0%}"), html.Span("median time saved")], className="dstat"),
    ], className="dstats", style={"marginBottom": "12px"}) if s else None
    table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ("ID", "Background", "By hand", "With app", "Quality hand / app",
                                                 "Useful", "Ease", "Would use", "Quote OK")])),
        html.Tbody([html.Tr([
            html.Td(r["label"]), html.Td(r["background"]), html.Td(_fmt(r["hand_seconds"])), html.Td(_fmt(r["app_seconds"])),
            html.Td(f"{r['ratings'].get('hand_quality')} / {r['ratings'].get('app_quality')}"),
            html.Td(r["ratings"].get("useful")), html.Td(r["ratings"].get("ease")), html.Td(r["ratings"].get("would_use")),
            html.Td(badge("yes", "ok") if r["consent"] else badge("no", "warn")),
        ]) for r in rows]),
    ], className="simple-table")
    quotes = [html.Blockquote([f"“{r['quote']}”", html.Span(f" — {r['label']}, {r['background']}", className="hint")],
                              className="study-quote") for r in rows if r["consent"] and r["quote"]]
    return html.Div([head, table, *quotes])


@callback(Output("st-csv", "data"), Input("st-csv-btn", "n_clicks"), prevent_initial_call=True)
def download(_):
    rows = completed_sessions()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "date", "background", "first_task", "hand_seconds", "app_seconds", "hand_quality", "app_quality",
                "useful", "ease", "would_use", "consent_to_quote", "quote", "improve"])
    for r in rows:
        g = r["ratings"]
        w.writerow([r["label"], r["ts"][:10], r["background"], r["first_task"], r["hand_seconds"], r["app_seconds"],
                    g.get("hand_quality"), g.get("app_quality"), g.get("useful"), g.get("ease"), g.get("would_use"),
                    r["consent"], r["quote"] if r["consent"] else "", r["improve"]])
    return dcc.send_string(buf.getvalue(), "superday_user_test.csv")


@callback(Output("st-results", "children", allow_duplicate=True), Output("st-del-pick", "options", allow_duplicate=True),
          Output("st-del-pick", "value"), Input("st-del", "n_clicks"), State("st-del-pick", "value"), prevent_initial_call=True)
def delete(_, sid):
    if not sid:
        return no_update, no_update, no_update
    db.execute("DELETE FROM study_sessions WHERE id = ?", (sid,))
    return results_view(), _session_options(), None
