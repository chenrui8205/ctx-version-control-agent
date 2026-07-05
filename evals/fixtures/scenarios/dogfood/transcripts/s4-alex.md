# chip-in — session 4 (alex) — thu 2026-07-04, afternoon
# raw log, condensed. perf pass on the expenses API. slammed today — skipped the
# context pull, just diving in from what I remember from Monday.

[14:02] alex: ok no time for ceremony today. GET /expenses got slow on my seeded db
        this morning, felt like a table scan. can you check the query plan before
        we touch anything?

[14:03] agent: Running EXPLAIN QUERY PLAN on the hot-path query:

        sqlite> EXPLAIN QUERY PLAN
           ...> SELECT * FROM expenses ORDER BY created_at DESC LIMIT ? OFFSET ?;
        QUERY PLAN
        `--SCAN expenses
        `--USE TEMP B-TREE FOR ORDER BY

        Full scan + temp b-tree for the sort. No index on created_at. Same story for
        the payer filter path (`WHERE payer = ?`) — also SCAN expenses.

[14:05] alex: yeah that tracks. add an index on created_at desc for the list
        endpoint, and one on payer while you're in there — the "who owes what"
        screen filters on payer constantly.

[14:06] agent: Added migration 0004_add_expense_indices.sql:

        CREATE INDEX idx_expenses_created_at ON expenses(created_at DESC);
        CREATE INDEX idx_expenses_payer ON expenses(payer);

        Applied to dev.db. Re-running EXPLAIN QUERY PLAN:

        sqlite> EXPLAIN QUERY PLAN SELECT * FROM expenses ORDER BY created_at DESC LIMIT ? OFFSET ?;
        QUERY PLAN
        `--SCAN expenses USING INDEX idx_expenses_created_at

        sqlite> EXPLAIN QUERY PLAN SELECT * FROM expenses WHERE payer = ? ORDER BY created_at DESC;
        QUERY PLAN
        `--SEARCH expenses USING INDEX idx_expenses_payer (payer=?)
        `--USE TEMP B-TREE FOR ORDER BY

        Temp b-tree is gone on the main list path; payer lookups now index searches.

[14:09] alex: nice. temp b-tree gone is the win I wanted. leave the payer sort
        b-tree alone, that result set is tiny per person anyway.

[14:11] alex: let me hammer it real quick so we have an actual number and not
        vibes. seeding 5k rows.

[14:12] alex: $ python scripts/seed.py --rows 5000
        seeded 5000 expenses across 6 payers

[14:14] alex: $ hey -z 60s -c 20 http://localhost:5000/expenses

        Summary:
          Requests/sec: 203.4412
        Latency distribution:
          50% in 0.0182 secs
          95% in 0.0361 secs
          99% in 0.0523 secs
        Status code distribution:
          [200] 12207 responses

        ~200 rps sustained, p95 36ms. zero 5xx, zero "database is locked" — WAL
        mode holding up fine under concurrent readers.

[14:16] agent: That's p95 under 40ms at ~200 rps on 5k rows. Caveat for the
        write-up: single laptop, hey on the same machine as the server, dev
        config — directional, not a capacity plan.

[14:17] alex: agreed, call it laptop-grade. still, good enough signal that
        sqlite+WAL isn't the bottleneck for a 12-person trip app lol.

[14:24] alex: while I'm writing up the perf notes — let's also get the paging
        behavior onto the wiki, people keep asking me on slack. GET /expenses
        returns 50 items per page by default. same as what I wrote down monday,
        use the same field name, get_expenses_default_page_size.

[14:25] agent: Noted for the context push: GET /expenses returns 50 items per
        page by default (get_expenses_default_page_size = 50).

[14:26] alex: yep. it IS 50, I set it up myself. clients override with ?limit=.

[14:31] alex: one more thing before I run — riley volunteered on slack to deploy
        a demo instance to fly.io so the group can poke at it before the trip.
        put that down as a next step, owner riley.

[14:32] agent: Added: next step — deploy Chip-in demo instance to fly.io, owner
        riley, open.

[14:33] alex: ok that's it, I'm getting pulled into the other thing. push the
        session context for me? no time to review pages today, just stage it and
        tell me if anything comes back weird.

[14:34] agent: Will do — extracting entries and pushing to Context VCS now.

# end of session log
