# S2 scorecard (Sam UI)
- planted dup (sqlite-concurrency paraphrase): DROPPED as duplicate conf .85 ✓ HEADLINE PASS
- planted lifecycle close (expenses-ui next_step): supersede/refines conf .97, x-collision-exempt status worked, no false conflict ✓
- cors finding + receipt question: new ✓ ; cors state_change: complementary keep ✓
- ACTION MISS (1/6): expenses-ui state_change classified refines->supersede of the SAME next_step target
  the close also superseded; second supersede won; state_change content ABSENT from master (12 rows, verified)
  => INCIDENT DF-1: (a) classifier: cross-type refines should be complementary [fixture candidate R22]
     (b) pipeline: no guard against 2 supersedes of one target in a batch — silent content loss; preview
     unfaithful (said supersede, effect = drop). Data-loss gate: FAIL (soft — content recoverable in entries store)
- action accuracy 5/6 ; recall 6/6 ; subject reuse: sqlite-concurrency ✓ expenses-ui ✓
- open set after S2: settle-up-cent-allocation, settle-up-algorithm, receipt-photo-uploads ✓ ; master≡HEAD ✓
- UX feedback: drop needs louder receipt w/ page link; fuzzy subject suggestions at stage time; client-side prevalidation
