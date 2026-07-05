# Chip-in — session 6 (riley) — Saturday 2026-07-04, morning
# wrap-up-the-week session. coffee #1.

[riley] morning. weekend wrap-up. pull context first — what's still open going into
the weekend? open threads + last few journal entries.

[agent] pulling. `ctxvcs page open-threads` + `journal --last 3`.

[agent] open threads as of e1f00fbd:
  1. receipt-photo-uploads — open_question (sam, since Monday): should v1 support
     attaching a receipt photo to an expense? non-blocking but schema implications
     (expense -> attachment) get pricier to retrofit. needs a team yes/no.
  2. demo-seed-data — next_step, owner sam: seed script, trip weekend, 4 people,
     8 expenses, at least one uneven split.
  3. chipin-demo-deploy — next_step, owner YOU: deploy demo to fly.io before the trip.
journal: sam built the settle-up UI last night (formatCents, integer cents end to end),
alex did the perf pass on GET /expenses (two indices, ~200rps p95 36ms), your session
before that shipped GET /settle-up + the cent-allocation decision.

[riley] huh — wasn't there a step for alex to review/harden the settle-up endpoint?
my Thursday session note literally said "Alex's settle-up next step stays open".
it's not in open-threads anymore.

[agent] correct, it's not on the open-threads page. sam's session last night touched
the settle-up view and verified against seeded data — plausibly alex or sam closed
the review during the week. want me to pull the settle-up-algorithm page and check
the close reason?

[riley] nah. it's saturday. if it dropped off open-threads I'll assume it got wrapped
up during the week. if it resurfaces, it resurfaces. moving on.

[riley] ok, my item first: the deploy. did it this morning before you woke up.
`fly launch`, wrote a small Dockerfile (python slim, uvicorn, nothing fancy),
made a fly volume and mounted it at /data, pointed the SQLite path there.
app is live: https://chip-in-demo.fly.dev — I hit it from my phone, added a
test expense, settle-up renders. group can poke at it before the trip.

[agent] nice. so chipin-demo-deploy is done — per the lifecycle rule that's a close:
push the next_step again with status: closed + what closed it, not a delete.
also worth an entry that the demo instance exists (URL, Dockerfile, volume)?

[riley] yes to both. and record one gotcha while it's fresh, because someone WILL
trip on it: fly.io machines suspend on idle, and SQLite lives on that single
volume. two consequences —
  1. occasional cold starts when the machine wakes up. fine for a demo, don't
     panic if the first request after lunch takes a few seconds.
  2. this is definitely NOT a multi-instance setup. one volume, one machine,
     SQLite. do not `fly scale count 2` and expect anything good.
if Chip-in ever grows past the trip demo, the storage layer is the first thing
to revisit. write that down as a constraint or finding, your call.

[agent] I'd file it as a constraint on the deploy subject — "single machine, single
volume, suspend-on-idle" is a hard operational boundary of the current setup, and
the "storage layer first if it grows" bit goes in the body. it's your deploy
experience so origin human.

[riley] fine. next: sam's receipt question. it's been sitting since monday and I
didn't want the schema to calcify around silence, so I put it to the group on
slack this morning. everyone was around (packing for the trip lol). DECIDED:
receipts are deferred to v2. v1 ships without attachments.

[agent] what was the alternative on the table?

[riley] shipping a minimal photo-upload in v1 — just an image blob per expense,
no processing. rejected: you immediately inherit storage (where do blobs live,
the fly volume? lol) plus moderation/liability questions, for a weekend app.
sam's own framing convinced everyone: nobody needs receipts to split a pizza.
schema stays clean, expense -> attachment can be designed properly in v2 if v2
ever exists.

[agent] recording as a decision (chosen: defer to v2; alternative: minimal v1
photo-upload, rejected for storage + moderation complexity) and closing sam's
open_question with a pointer to the decision. both origin human — team call,
you relayed it.

[riley] yep. last thing, then I'm going to pack. looking at the live URL made me
slightly itchy: chip-in-demo.fly.dev is public. anyone with the URL can post
expenses — there's zero auth, not even a shared PIN. fine while it's just the
four of us, but if the link leaks beyond the group it's an open guestbook with
a balances feature.

[agent] want me to open it as a question rather than a task? nobody's decided
anything and it shouldn't block the trip.

[riley] exactly. open question for next week: does Chip-in need real
authentication before the group shares the URL beyond the four of us? not
blocking, no owner. team can chew on it monday.

[agent] got it. so the push list for this session:
  - close chipin-demo-deploy next_step (deployed, live URL)
  - state_change: demo deployed via fly launch, Dockerfile, SQLite volume at /data,
    https://chip-in-demo.fly.dev
  - constraint: fly suspend-on-idle + single-volume SQLite -> cold starts, no
    multi-instance; storage layer first thing to revisit if it grows
  - decision: receipts deferred to v2 (alt: minimal v1 upload, rejected)
  - close receipt-photo-uploads open_question
  - new open_question: public demo URL, does it need real auth before wider sharing
nothing on demo-seed-data (sam's, untouched), nothing on settle-up (observed the
review step gone from open-threads, assumed closed during the week, no action).

[riley] that's the week. stage it, show me the preview, commit if clean. if
anything conflicts, stop and show me — do not resolve on my behalf on a saturday.

[agent] staging now.
