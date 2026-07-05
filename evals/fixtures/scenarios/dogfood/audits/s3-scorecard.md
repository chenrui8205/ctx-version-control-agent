# S3 scorecard (Riley: rounding decision + settle-up + R06 trap)
- R06 TRAP: collision on get_expenses_default_page_size WITH change language => refines conf .97, clean
  supersede, NO MR, Facts=20 post-commit. HEADLINE PASS (the false-conflict guard held live)
- lifecycle close of cent-allocation question: supersede ✓
- NP-hard finding: complementary keep ✓
- ACTION MISSES (2/5 wrong => 3/5 accuracy):
  * decision entry => refines/supersede of the SAME question target as the close => DECISION RECORD LOST
    from master (verified: only closed question under 5009cb69). DF-1 recurrence, higher-value casualty.
  * state_change settle-up => refines/supersede of ALEX'S OPEN next_step (body explicitly said step stays
    open) => step retired from open-threads. NEW: DF-2 cross-type supersede retiring open work.
- open set after S3: ground truth {settle-up-algorithm, receipt-photo-uploads}; actual {receipt-photo-uploads}
  => DIVERGENCE (DF-2)
- extraction recall 5/5, subject+FIELD-NAME reuse perfect (wiki Facts read paid off), origin tags correct
- master≡HEAD ✓ ; false-conflict gate ✓ ; data-loss gate FAIL (DF-1b, unlabeled drop of a decision)
- agent-suggested UX: preview should state consequences ("this will remove X from open-threads");
  per-action override instead of abort-all; classifier rationale visible per row (it was)
- SYSTEMATIC PATTERN: "same subject + newer => refines" prior over-fires on CROSS-TYPE pairs, esp. vs
  lifecycle types (open_question/next_step). 3 of 3 damage events share this root.
