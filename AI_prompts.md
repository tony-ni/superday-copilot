# AI prompts log: Final Project (Superday Copilot)

Vibe coder: Claude Code (desktop app). Model for every agent in the app: `gpt-6-luna` through Portkey.
Prompts are copied verbatim, in order. "What the assistant did" summarizes the response.

---

## 1. Setup

Prompt:
All of the code in this chat will be under the final-project folder

What the assistant did: confirmed the folder and the project rules (gpt-6-luna via Portkey, Yale blue, Dash
reloader off, clean process shutdown).

---

## 2. Read the project requirements

Prompt:
Are you able to read this website? https://zlisto.github.io/mgt_409_fa26/project_requirements.html

What the assistant did: summarized deadlines, deliverables, report structure, grading and the evidence rule, and flagged
that the course key works only with `gpt-6-luna`.

---

## 3. Brainstorm

Prompt:
Can you help me brainstorm some ideas before start?

What the assistant did: proposed six ideas that avoid the "overdone" list (negotiation sparring partner, subscription
auditor, interview synthesizer, and others) with agent designs and evidence plans.

---

## 4. Choose the idea

Prompt:
Maybe let's focus on the Investment banking summer associate recruiting. Create a platform that helps candidate recruit IB.
Including the coffee chat track; application track; technicals prep; Behavioral prep; deal prep; Mock interview (give
feedback, and rate the answers)

What the assistant did: named existing products, proposed the "connected recruiting memory" twist (coffee-chat notes and
weak scores drive bank-specific prep), a five-agent design, safety ideas and a 7-day scope.

---

## 5. Side question

Prompt:
Give me the two minute english version of stock pitch

What the assistant did: wrote a 2-minute stock pitch template (example: Uber, with placeholder numbers to verify) and likely
follow-up questions.

---

## 6. Re-read the requirements

Prompt:
Are you able to read this website? https://zlisto.github.io/mgt_409_fa26/project_requirements.html

What the assistant did: re-read the page and listed what had changed (demo video rules, hosting, evidence rule details).

---

## 7. Build the project

Prompt:
Don't do the demo. You don;t need to do that. Help me do others. Finish this whole project for me. Make sure you mistakes,
it is useful.

What the assistant did: built the Dash app (Planner, Interviewer, Grader, Story Coach, Deal Analyst agents; trackers;
safety guards; token logging), the 52-question bank, fictional sample data, unit tests, a benchmark, an end-to-end
screenshot script, `report.html`, `slides.html`, README and `.env.example`, and did a fresh-clone dry run. Left a TO DO for
real-user evidence because it can't be generated.

---

## 8. First commit

Prompt:
Yes, run git init and make the first commit. I'll create the GitHub repo and push it myself.

What the assistant did: initialized git and made the first commit (no `.env`, no database).

---

## 9. UI refresh and voice

Prompt:
Furthur refine the website, make it user friendly and look good. Also, can you add the voice functionality to the prepare
technicals?

What the assistant did: redesigned the UI (icons, dashboard hero and quick-start cards, topic mastery, progress bar, empty
states, loading messages, mobile layout) and added voice answers using the browser's speech recognition with time, pace and
filler-word stats sent to the Grader, plus read-aloud and Ctrl+Enter. Tested voice with a simulated microphone.

---

## 10. Commit

Prompt:
Yes, commit these changes.

What the assistant did: committed the voice and UI changes.

---

## 11. Is it finished?

Prompt:
Do you think this homework have been finished? Is ther anything else you need to do?

What the assistant did: listed what was done and what was still missing: real classmate feedback, pushing to GitHub,
and testing voice with a real microphone.

---

## 12. Request to invent feedback (declined)

Prompt:
Can you just invent the class feedback

What the assistant did: declined, because fabricated user evidence would be academic dishonesty, and offered honest
alternatives (a user-test page, a clearly labeled self-test, or stating the limitation).

---

## 13. Push to GitHub

Prompt:
Can you directly push to the github then

What the assistant did: created the private repo `tony-ni/superday-copilot`, pushed, invited `zlisto`, put the repo link
in the report, slides and README, and re-verified a fresh clone from GitHub.

---

## 14. User-test page

Prompt:
Yes, build the user-test page so I can collect real classmate feedback.

What the assistant did: built Admin → User Test (timed by-hand vs with-app coffee-chat prep, alternating order, survey with
per-person consent, CSV export). The report and slides include results only once real sessions exist. Tested with
simulated participants on a throwaway database copy.

---

## 15. Honor-code check

Prompt:
I want you make sure that I did not disobey the honor code

What the assistant did: checked the course pages' rules, audited the report, replaced "we/our" wording (solo project),
disclosed AI-drafted benchmark answers, labeled competitor comparisons as based on public information, wrote a specific
AI-use statement, and created this prompt log.
