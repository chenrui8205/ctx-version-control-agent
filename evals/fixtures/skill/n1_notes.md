# quick notes, friday pm (raw notes — N1 fixture: closes an existing open thread)

- FINALLY finished the dlq replay runbook. it's in the oncall wiki, linked from the
  ban-service page. that todo can go away
- while writing it i hit something worth flagging: replay ordering is NOT guaranteed —
  replayed messages get appended to the tail of the topic, so consumers can see a
  replayed event AFTER newer events. put a big warning section in the runbook about it
- talked it over with kevin and we decided: replays stay MANUAL-ONLY for now, no
  auto-replay cron. alternative was a nightly auto-replay job but it's too risky until
  idempotency keys land. revisit after that
- todo for next week: add idempotency keys to the ban consumer (mine)
