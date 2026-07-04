# T1 — ban-lifecycle implementation session (condensed log)

DEV: Today I want to close out the ban event emission path. Last week's problem was
the dual-write gap between the bans table and the event stream.

AGENT: Recap: writing the ban row and publishing the event separately can strand
either side on a crash. Options: transactional outbox table, RocketMQ transactional
half-messages, or CDC via Debezium. Half-messages avoid a poller and we already run
RocketMQ 5.x, which supports them on our cluster tier.

DEV: We debated this in standup too. Let's go with RocketMQ transactional
half-messages — outbox means another table plus a relay we have to operate, and CDC
is overkill for one topic. Decision made, write it down.

AGENT: Implementing. [edits ban_service/emitter.py, wires TransactionMQProducer,
local transaction executor commits the DB row then confirms the half-message]

AGENT: While testing I confirmed from the RocketMQ docs and our cluster config:
delivery on this cluster is at-least-once — duplicate deliveries WILL happen on
consumer redelivery, so every consumer of ban-lifecycle events must be idempotent.
I verified our consumer dedupes on (ban_id, version) so we're safe, but this is a
standing property of the pipeline worth recording.

AGENT: Second thing I found while poking the broker: messages that exhaust the retry
policy (16 attempts by default) land in the per-group DLQ topic %DLQ%ban-consumer,
and nothing currently consumes or alerts on it. Confirmed by publishing a poison
message on staging — it sat in the DLQ silently.

DEV: Ugh, silent DLQ is scary. We can't leave that. Put it on the list: someone needs
to write the DLQ replay runbook and wire an alert. I'll own finding an owner.

AGENT: Noted as an open next step. Emitter change is merged to main (PR #412) and
deployed to staging; prod rollout is gated on the canary window tomorrow.
