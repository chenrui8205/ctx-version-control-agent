# chip-in session — sam — mon 2026-07-04, afternoon

[13:12] sam: ok new project. alex pinged me this morning saying he pushed the kickoff
context. pull it before we touch anything — what's the current state?

[13:12] agent: pulled open-threads + last journal entry from ctxvcs.
- YOUR thread: `expenses-ui` — "Sam builds the add-expense form and balances UI in
  vanilla JS against POST /expenses and GET /expenses." owner: sam.
- hard constraint `money-representation`: ALL money is integer cents. DB, API, and
  **the JS**. non-negotiable (alex got burned by float money twice at work).
- `expenses-api` page: POST /expenses validates positive integer amount_cents,
  non-empty participants, returns 201. GET /expenses is newest-first, paginated
  page/page_size, default 50.
- also open (not ours): settle-up algorithm (alex) and a blocking question about
  leftover-cent allocation ($100/3 problem) — alex raising at standup.

[13:14] sam: cool, so cents-in-cents-out even in the form. dollars in the input box,
multiply by 100 before POST, never touch floats after that. let's go. static/index.html
+ app.js, no framework.

[13:20] agent: scaffolded static/index.html + static/app.js. form: description,
amount ($ text input), payer, participants as comma-separated names for now.
`toCents()` does `Math.round(parseFloat(v) * 100)` then integer-checks — rejects
anything that doesn't survive the round-trip, so "10.999" errors instead of lying.

[13:26] sam: run it. `python -m http.server 5500` in static/, uvicorn on 8000.

[13:27] agent: form renders. submitting...

[13:28] agent: POST failed. console: "Access to fetch at 'http://localhost:8000/expenses'
from origin 'http://localhost:5500' has been blocked by CORS policy: No
'Access-Control-Allow-Origin' header is present on the requested resource."

[13:29] sam: ugh. right, different port = different origin. isn't there a fastapi thing
for this?

[13:33] agent: yes — `CORSMiddleware` from fastapi.middleware.cors. added it with
`allow_origins=["*"]` to unblock.

[13:36] sam: still failing?? the preflight passes now but the actual fetch dies.

[13:38] agent: you have `credentials: "include"` on the fetch (from the boilerplate I
copied for the session-cookie idea). per the fetch spec, a wildcard
Access-Control-Allow-Origin is NOT valid for credentialed requests — the browser
requires an explicit origin echoed back, and it fails silently-ish (generic CORS error,
nothing on the server side, server never logs an error because the request completed).

[13:41] sam: so `*` + cookies = dead, and nothing tells you why. lovely. we don't even
use cookies yet — but leave credentials on, we will. fix it properly.

[13:44] agent: changed to `allow_origins=["http://localhost:5500", "http://localhost:8000"]`,
`allow_credentials=True`, allow_methods/headers `["*"]`. POST goes through, 201.

[13:47] sam: ...that ate 40 minutes of my life. write that one down for the team —
"add CORSMiddleware" everyone knows, the wildcard-vs-credentials trap nobody knows
until it bites them.

[13:48] agent: noted as a finding.

[13:50] sam: ok, balances view. GET /expenses, split each expense evenly across its
participants, payer gets credited what others owe. all integer math.

[14:05] agent: balances table rendering. per expense: `share = Math.floor(amount_cents
/ participants.length)` for each participant, payer credited `amount_cents - own share`.
leftover cents from the floor currently just... stay with the payer implicitly. note:
this is exactly alex's open cent-allocation question — I did NOT pick a policy, the
view just shows per-person nets; whatever standup decides slots into one function.

[14:06] sam: good, don't decide that for alex. seed some test expenses.

[14:11] agent: seeded 6 expenses via the form: groceries $84.30 sam→(sam,alex,priya),
pizza $41.00 alex→(sam,alex), climbing $66.00 priya→(all)... balances table checks
out against hand math. newest-first list matches GET ordering.

[14:15] sam: hey wait — random thought. tonight alex is going to be hammering this
same sqlite file with his settle-up stuff while I'm clicking around the UI. can sqlite
even handle two of us hitting it at once? or is this thing going to lock up mid-demo?

[14:16] agent: let me check rather than guess.

[14:19] agent: researched it: SQLite allows exactly ONE writer at a time —
concurrent writes serialize, a second writer waits (or gets SQLITE_BUSY past the
busy_timeout). BUT in WAL journal mode, readers don't block while a write is in
progress — they read a consistent snapshot from before the write. so your GET
polling stays smooth even during alex's inserts. writes-vs-writes still serialize,
but for two devs + a handful of phone clients that's a non-issue.

[14:21] sam: so single writer, but WAL means readers ride through writes. that's
actually reassuring — and worth sharing, I don't think anyone's written that down.
flag it for the push.

[14:22] agent: will do.

[14:35] sam: polish pass — clear form on success, red inline error on 4xx, balances
auto-refresh after add. and commas in participant names will break my split, add a trim
+ dedupe.

[14:48] agent: done. also amounts render as dollars via `(cents/100).toFixed(2)` at
display time only — cents everywhere else, per alex's constraint.

[14:52] sam: demo run... add expense, list updates, balances update. that's the whole
`expenses-ui` next step alex left me. it's DONE — close it out when we push, however
the skill wants lifecycle closes done (new version with status closed, I think).

[14:53] agent: correct — closing is a push of a new version with status: closed, not
a delete.

[14:58] sam: one last thing before we wrap. splitting dinner receipts by hand made me
think — should v1 let people attach a receipt photo to an expense? nobody's discussed
it, it's not blocking anything, I don't even know if I want it. but somebody should
decide before the schema calcifies. leave it as an open question for the team,
non-blocking.

[14:59] agent: logged. pushing session context to ctxvcs now: state change (UI built),
CORS finding, sqlite concurrency finding, close expenses-ui, open receipt-photos
question.

[15:00] sam: ship it.
