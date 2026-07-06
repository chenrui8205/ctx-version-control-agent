# monday standup notes (raw notes — N2 fixture: must reuse >= 2 registry subjects)

- bumped the ban-service consumer batch size 32 -> 64 after friday's backlog scare.
  queue drains about 2x faster now, no timeout errors over the weekend
- yoti sandbox creds finally arrived. ran the age estimation flow end to end in
  staging — works, roughly 1.4s p50 per check. good enough for the AU flow
- open question to park for the team: what do we do with users who fail age
  estimation twice? no answer yet, not blocking this sprint
