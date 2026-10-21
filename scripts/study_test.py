"""Browser test for the User Test page: runs two simulated participants end to end.

Run it against a COPY of the database so no test data mixes with real classmate results:
    set SUPERDAY_DB=<copy.db> and PORT=8052, start `python app.py`, then:
    python scripts/study_test.py 8052
Makes two real app-draft calls (about $0.001).
"""

import sys

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8052"
BASE = f"http://127.0.0.1:{PORT}"
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))


def run_participant(pg, n, hand_secs):
    pg.goto(BASE + "/study")
    pg.wait_for_selector("#st-begin")
    pg.fill("#st-name", f"Test {n}")
    pg.check("#st-consent input")
    pg.click("#st-begin")
    pg.wait_for_function("() => document.getElementById('st-setup').style.display === 'none'")
    order = []
    for _ in range(2):
        pg.wait_for_function("() => ['st-p-hand','st-p-app'].some(i => document.getElementById(i).style.display !== 'none')")
        kind = "hand" if pg.is_visible("#st-p-hand") else "app"
        order.append(kind)
        if kind == "hand":
            pg.click("#st-hand-start")
            pg.wait_for_timeout(hand_secs * 1000)
            check(f"P{n} hand clock runs", ":" in pg.inner_text("#st-hand-clock"), pg.inner_text("#st-hand-clock"))
            pg.fill("#st-hand-text", "30-second intro: I'm Alex, FP&A at a CPG company...\nQuestions:\n1. a\n2. b\n3. c")
            pg.click("#st-hand-done")
        else:
            pg.click("#st-app-start")
            pg.wait_for_function("() => document.getElementById('st-app-text').value.includes('Questions to ask')", timeout=120_000)
            draft = pg.input_value("#st-app-text")
            check(f"P{n} app draft generated", "30-second intro" in draft, draft[:60].replace("\n", " "))
            pg.fill("#st-app-text", draft.split("(Edit this")[0].strip())
            pg.click("#st-app-done")
        pg.wait_for_timeout(800)
    check(f"P{n} order", order == (["hand", "app"] if n % 2 == 1 else ["app", "hand"]), str(order))
    pg.wait_for_selector("#st-p-survey", state="visible")
    for q, v in (("st-q-hand", "3"), ("st-q-app", "4"), ("st-q-useful", "5"), ("st-q-ease", "4")):
        pg.check(f"#{q} input[value='{v}']")
    pg.check("#st-q-use input[value='Yes, weekly']")
    pg.fill("#st-quote", f"Test quote from participant {n}.")
    pg.click("#st-submit")
    pg.wait_for_function("() => document.getElementById('st-setup').style.display !== 'none'")
    check(f"P{n} form reset for next participant (consent unticked)",
          pg.input_value("#st-name") == "" and not pg.is_checked("#st-consent input"))


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 950}, accept_downloads=True)
    run_participant(pg, 1, 4)
    run_participant(pg, 2, 3)
    res = pg.inner_text("#st-results")
    check("results table lists P1 and P2", "P1" in res and "P2" in res, res[:120].replace("\n", " | "))
    check("summary shows medians", "median by hand" in res and "median with app" in res)
    check("consented quote shown", "Test quote from participant 1" in res)
    with pg.expect_download() as dl:
        pg.click("#st-csv-btn")
    text = open(dl.value.path(), encoding="utf-8").read()
    check("CSV export has both participants", text.count("\nP") == 2, text.splitlines()[0][:60])
    pg.screenshot(path=sys.argv[2] if len(sys.argv) > 2 else "study_check.png", full_page=True)
    b.close()
sys.exit(0 if ok else 1)
