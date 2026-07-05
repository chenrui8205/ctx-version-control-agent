# Session 1 — Alex + agent — Mon 2026-07-04, ~9:10am
# Project: Chip-in (expense splitting for the group trip)

[alex] ok kickoff. sam and riley are doing the trip planning doc, I said I'd get the
backend skeleton up before standup. new project "chip-in" — split expenses for the
Tahoe trip. toy app, but let's not make it garbage.

[alex] first: stack. I went back and forth over the weekend. options I considered:
  - Flask + Postgres — rejected. Postgres means running a DB somewhere, migrations,
    connection strings in three places. way too much ops for a weekend project.
  - Express + SQLite — rejected. backend in JS means Sam and I both context-switch
    for no reason. nobody wants that.
  - FastAPI + SQLite + vanilla JS on the front. <- this one. zero-ops, everyone on
    the team knows Python, and FastAPI gives us pydantic validation for free.
DECISION: FastAPI + SQLite + vanilla JS. done deliberating.

[agent] Noted. Want me to scaffold? Suggest: chipin/ with app/main.py, app/db.py,
app/models.py, a pyproject, and a static/ dir for the vanilla JS front.

[alex] yes. also data model — I thought about this in the shower. we could do it
"properly": expenses table + expense_participants junction table, normalized. but
for a weekend project that's schema ceremony. every query we actually need is
"give me expenses and who's in them". so:
DECISION: single `expenses` table with a `participants` JSON column (array of
member names). if the queries get hairy later we revisit and normalize. schema
speed > purity here.

[agent] OK. Scaffolding now.

  $ mkdir -p chipin/app chipin/static
  $ cd chipin && uv init --name chipin
  $ uv add fastapi uvicorn

[agent] Created app/main.py, app/db.py, app/models.py. Schema:

  CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    payer TEXT NOT NULL,
    participants TEXT NOT NULL,  -- JSON array
    created_at TEXT DEFAULT (datetime('now'))
  );

[alex] hold on — amount_cents, good, you read my mind. let me make this explicit
because I've been burned by this at work TWICE: ALL money amounts in this app are
stored as integer cents. never floats. not in the DB, not in the API, not in the
JS. if I see a 0.1 + 0.2 anywhere I'm reverting the commit. non-negotiable.

[agent] Understood — treating that as a hard constraint. Pydantic model uses
`amount_cents: int` with `gt=0`, and I'll leave a comment in models.py.

[agent] Implemented POST /expenses:
  - body: {description, amount_cents, payer, participants: [str]}
  - validates participants non-empty, amount_cents positive int
  - returns 201 with the created row

[agent] Implemented GET /expenses:
  - returns newest-first
  - paginated: `page` + `page_size` query params, default page_size=50

[alex] 50 per page is fine, it's like 8 people on this trip. run it.

  $ uv run uvicorn app.main:app --port 8001 &
  $ curl -s -X POST localhost:8001/expenses -H 'content-type: application/json' \
      -d '{"description":"cabin deposit","amount_cents":42000,"payer":"alex",
           "participants":["alex","sam","riley"]}'
  -> 201 {"id":1,"description":"cabin deposit","amount_cents":42000,...}
  $ curl -s localhost:8001/expenses | jq '.items | length'
  -> 1

[alex] good. one thing nagging me — sam's UI will poll GET /expenses while people
add stuff on their phones. is sqlite going to fall over with concurrent hits?

[agent] Let me check the SQLite docs on this rather than guess.

[agent] Research findings on SQLite concurrency:
  - In the default journal mode (rollback journal), a write transaction takes a
    lock that blocks concurrent writers — writers queue up, and readers can block
    a writer / a writer blocks readers during the commit window.
  - Enabling WAL (write-ahead logging) mode changes this: readers keep reading
    a consistent snapshot while a write is in progress — concurrent readers + one
    writer coexist fine.
  - Caveat either way: SQLite still enforces a SINGLE writer at a time. WAL does
    not give you concurrent writes, it gives you readers-don't-block-on-writes.
  For a handful of phones hitting this, WAL is plenty. Sources: sqlite.org WAL
  docs + the "SQLite in busy apps" section of the appropriate-uses page.

[alex] good enough, turn it on.

[agent] Done — `PRAGMA journal_mode=WAL` on connection setup in app/db.py.
Verified: `sqlite3 chipin.db 'PRAGMA journal_mode;'` -> wal

[alex] ok next: I started sketching settle-up on paper and hit a real question.
say the cabin is 42000 cents split 3 ways, fine, 14000 each. but $100 split 3 ways
is 3333.33... cents don't divide. who eats the leftover cent(s)? options I can
think of: payer absorbs it, round-robin the extra cents, deterministic by sorted
name, largest-remainder... I genuinely don't know what feels fair and I don't want
to pick this alone since it changes everyone's balances.

[agent] Want me to log it as an open question rather than deciding now?

[alex] yes — and flag that it BLOCKS the settle-up feature. can't compute
transfers until allocation is defined. I'll raise it at standup.

[alex] wrapping up. next steps for the week, agreed with sam on slack just now:
  - sam: add-expense form + balances UI (vanilla JS against the two endpoints)
  - me (alex): minimal-transfers settle-up algorithm — fewest payments that zero
    out balances. blocked on the cent-allocation question above, but I can start
    on the graph part.

[alex] push this session to ctxvcs so sam and riley see it before their sessions.

[agent] Pushing. Summary of the session: stack + data model decided, repo
scaffolded with POST/GET /expenses working, WAL enabled after concurrency
research, integer-cents constraint on record, one blocking open question, two
next steps assigned.
