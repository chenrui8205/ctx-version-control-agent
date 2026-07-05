# Chip-in — session 3 (Wednesday) — Riley Park + agent
# raw condensed log, times approximate

[09:12] riley> morning. pull the team context before I touch anything — what's open?

[09:13] agent> Pulled open-threads + last 2 journal entries from ctxvcs:
  - settle-up-cent-allocation (open_question, BLOCKING): how to allocate leftover
    cents when an amount doesn't split evenly ($100/3). Options floated Monday:
    payer absorbs / round-robin / deterministic by sorted name / largest-remainder.
    No decision. Alex was going to raise it at standup.
  - settle-up-algorithm (next_step, owner alex): minimal-transfers algorithm.
    "Partially blocked on cent allocation, but the graph part can start now."
  - receipt-photo-uploads (open_question, non-blocking, sam's).
  Last session: Sam shipped the add-expense form + balances view, fought CORS for
  40 min (wildcard origin + credentialed fetch = silent death), added CORSMiddleware
  with explicit origins.

[09:15] riley> ok. the cent thing is mine to kill today — standup didn't get to it
  monday and it's blocking everything settle-up shaped. I'm taking it to the
  whiteboard with coffee. meanwhile: the graph part of settle-up isn't blocked,
  and alex said as much. start sketching the endpoint, but it's his next_step so
  don't go marking anything of his done.

[09:16] agent> Understood. I'll draft the settle-up endpoint against current
  balances and leave alex's next_step untouched. Constraint check: all money is
  integer cents (money-representation, hard constraint) — no floats anywhere.

[09:17] riley> correct, alex will end you if a float shows up. back in an hour.

--- whiteboard interlude, ~10:20 ---

[10:24] riley> ok, cent allocation. I filled a whiteboard and here's where I landed:
  LARGEST-REMAINDER allocation, and the PAYER absorbs any residual cent.
  So: floor everyone's share, then hand out the leftover cents one at a time to
  the participants with the largest fractional remainders; if there's still a
  residual cent after that (rounding edge), the payer eats it.

[10:25] agent> Want the alternatives on record for the writeup?

[10:26] riley> yes. considered and REJECTED:
  - round-robin extra cents: order-dependent. whoever's first in the list pays
    more, and the "order" is an accident of insertion. confusing to explain.
  - random assignment: non-deterministic. can't write a test that asserts an
    exact split, and two clients computing the split disagree. dead on arrival.
  rationale for largest-remainder + payer-absorbs: it's deterministic, it's
  testable, and the payer eating at most one cent per expense is socially fine —
  you paid the bill, you can spare a penny. posted it in slack, alex 👍 sam 👍.
  team's agreed. that question is CLOSED — make sure the push reflects that,
  don't just leave it dangling open.

[10:27] agent> Logged. On push I'll close settle-up-cent-allocation (status:
  closed, body says what closed it) and record the decision separately with the
  rejected alternatives. Meanwhile — settle-up endpoint status:

[10:28] agent> Implemented GET /settle-up in chipin/app/main.py:
  1. compute net balance per person from all expenses (integer cents,
     largest-remainder split per your decision, payer absorbs residual)
  2. greedy min-cash-flow: repeatedly match the largest debtor with the
     largest creditor, transfer min(|debt|, credit), repeat until all zero.
  Returns a list of {from, to, amount_cents} transfers.

[10:31] riley> greedy — how bad can it be vs the true minimum number of transfers?

[10:36] agent> Researched it: computing the true minimum NUMBER of transfers is
  NP-hard in general — it reduces to partitioning people into zero-sum subsets
  (subset-sum flavored), so exact minimality doesn't scale. The greedy
  largest-debtor/largest-creditor approach guarantees at most n-1 transfers for
  n people (each matching step zeroes out at least one person), and it's the
  standard practical choice — it's what the Splitwise-style writeups converge on.
  For a household-sized n, nobody will ever notice the difference.

[10:37] riley> n-1 for a group of 5 is fine forever. note the NP-hard thing in the
  push though, it's exactly the kind of trivia the next person will re-research.
  and again — endpoint exists now, but it's alex's item and he may still want to
  review/harden it (edge cases, empty group, self-payments). leave his next_step
  open, just note the endpoint is there.

[10:38] agent> Noted. Tests: 100/3 split -> [3334, 3333, 3333] with payer holding
  the 3334 share via largest-remainder tie-break... actually tie-break goes to
  payer-absorbs only for the residual; remainder distribution is by fractional
  part, ties broken by sorted name for determinism. 6 unit tests green.

[10:39] riley> good. lunch.

--- lunch, testing on phone ---

[13:05] riley> back. tested the balances view on my phone over lunch and the
  expense list is SLUGGISH. scroll jank on first load. sam's UI is fine, I think
  it's just rendering too many rows at once. what does the API default to?

[13:06] agent> Checked the expenses-api subject page on the wiki: Facts table
  says get_expenses_default_page_size = 50 (set when alex scaffolded GET
  /expenses, paginated via page/page_size, newest-first).

[13:08] riley> 50 rows of expense DOM on a mid phone, yeah that's the jank.
  change the default page size to 20. UI already paginates so nothing breaks,
  first paint gets 2.5x lighter.

[13:09] agent> Done — GET /expenses default page_size 50 -> 20 in
  chipin/app/main.py. curl without params returns 20 items; page=2 works;
  explicit page_size still respected. Sam's UI re-checked, pagination still fine.

[13:10] riley> for the notes, be explicit that this is a change we made THIS
  session: "changed GET /expenses default page size from 50 to 20 after mobile
  render lag". not a bare fact — a change. the wiki tracks the field, keep the
  same field name it already uses.

[13:11] agent> Will do — get_expenses_default_page_size: 20, change-language body.

[15:40] riley> wrapping up. recap before you push?

[15:41] agent> Session recap:
  - DECIDED (you, team ratified on slack): cent allocation = largest-remainder,
    payer absorbs residual cent. round-robin and random rejected. Closes the
    blocking settle-up-cent-allocation question.
  - IMPLEMENTED (me): GET /settle-up, greedy min-cash-flow, ≤ n-1 transfers.
    alex's next_step stays open — his to review/harden.
  - RESEARCHED (me): true min transfer count is NP-hard; greedy n-1 is the
    standard practical answer.
  - CHANGED (this session): GET /expenses default page size 50 -> 20 after
    mobile render lag.
  - no new questions opened today.

[15:42] riley> that's the session. push it.
