"""Superday Copilot: an AI agent team for investment banking Summer Associate recruiting.

Run:  python app.py   then open http://127.0.0.1:8050
"""

from __future__ import annotations

import os

from dash import Dash, Input, Output, dcc, html

from superday import config, db

db.init()

from superday.pages import applications, behavioral, chats, dashboard, deals, mock, technicals, usage  # noqa: E402

PAGES = {
    "/": ("Dashboard", dashboard),
    "/mock": ("Mock Interview", mock),
    "/technicals": ("Technicals", technicals),
    "/behavioral": ("Behavioral & Story", behavioral),
    "/deals": ("Deal Prep", deals),
    "/chats": ("Coffee Chats", chats),
    "/applications": ("Applications", applications),
    "/usage": ("Usage & Safety", usage),
}
NAV_SECTIONS = [("Plan", ["/"]), ("Prepare", ["/mock", "/technicals", "/behavioral", "/deals"]),
                ("Track", ["/chats", "/applications"]), ("Admin", ["/usage"])]

app = Dash(__name__, title="Superday Copilot", suppress_callback_exceptions=True, update_title=None)
server = app.server


def sidebar(path):
    items = []
    for section, paths in NAV_SECTIONS:
        items.append(html.Div(section, className="nav-section"))
        items += [dcc.Link(PAGES[p][0], href=p, className="nav-link" + (" active" if p == path else "")) for p in paths]
    return items


def topbar():
    key = config.provider()
    status = f"AI: {config.MODEL} via {key[0].title()}" if key else "AI offline: add PORTKEY_API_KEY to .env"
    return html.Div([
        html.Div([html.Div("S", className="brand-mark"), "Superday Copilot", html.Small("IB recruiting, end to end")],
                 className="brand"),
        html.Div([html.Span(status), html.Span(id="topbar-spend")], className="topbar-meta"),
    ], className="topbar")


app.layout = html.Div([
    dcc.Location(id="url"),
    topbar(),
    html.Div([html.Nav(id="sidebar", className="sidebar"), html.Main(id="page", className="content")], className="shell"),
])


@app.callback(Output("page", "children"), Output("sidebar", "children"), Output("topbar-spend", "children"),
              Input("url", "pathname"), Input("url", "search"))
def route(path, search):
    path = path if path in PAGES else "/"
    module = PAGES[path][1]
    body = module.layout(search or "") if path == "/usage" else module.layout()
    return body, sidebar(path), f"Spend today: ${db.spend_today():.4f}"


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8050"))
    print(f"Superday Copilot running at http://127.0.0.1:{port}")
    if not config.provider():
        print("WARNING: no PORTKEY_API_KEY / OPENAI_API_KEY found in .env (repo folder or one level up). "
              "Trackers work, AI features will show an error.")
    # debug off and no reloader, so one edit never spawns a second server
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
