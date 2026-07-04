# T3 — follow-up session on the ban consumer + DLQ work (condensed log)
# Registry is pre-seeded (t3_registry.json). This session's content maps onto
# EXISTING subjects — the eval tests reuse, not invention.

DEV: Picking up from last week. First: the consumer timeout. Load test results?

AGENT: Ran the k6 soak overnight against staging. With the 60s consumer timeout, slow
downstream calls pile up and redelivery storms start at ~1400 rps. Dropping the
timeout to 30s cleared it: p99 consume latency 2.1s, zero redelivery storms across
three runs.

DEV: Then make it 30s. Ship the config change.

AGENT: Done — changed the ban-service consumer timeout from 60s to 30s in
ban-service/config/consumer.yaml, deployed to staging and prod behind the ops flag.
[state changed]

AGENT: Also, while in the broker console I measured the DLQ topic's retention: it is
48 hours on this cluster, inherited from the cluster default — NOT the 7 days the
oncall doc assumes. Replays later than two days are impossible today. Recorded as a
finding against the consumer pipeline.

DEV: Good catch. And the runbook I owed from last time — I finished it this morning,
it's in the oncall wiki and linked from the pager rotation page. Close that step out.

AGENT: Closing it. One question this raises: when we replay a large DLQ batch, should
replays be capped per tenant so one tenant's poison backlog can't starve the others?
The runbook doesn't cover it and it changes the replay tooling design.

DEV: Open question, not blocking — note it against the runbook work and we'll take it
to the infra sync.
