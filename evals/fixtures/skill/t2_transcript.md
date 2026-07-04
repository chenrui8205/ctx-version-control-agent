# T2 — age-verification vendor evaluation (condensed log)

DEV: We need to pick the age-assurance vendor for the AU under-16 rules. What are the
real constraints again?

AGENT: The eSafety Commissioner's guidance: platforms must have age assurance in place
when enforcement of the social-media minimum-age law begins on 10 Dec 2025. That date
is statutory — it does not slip with our roadmap. Treat it as a hard legal constraint
on everything downstream.

DEV: Right. And the shortlist?

AGENT: Three candidates evaluated this week: Yoti (facial age estimation, no document
retained, ~1.3% mean absolute error in the 13–17 band), Veriff (document-based,
higher friction, strongest audit trail), and AWS Rekognition (cheapest, but no
published under-18 error bands and no AU DP assessment). Yoti's estimation returns a
confidence score per check; below-threshold checks would need a fallback path.

DEV: Friction kills signup, and legal already cleared Yoti's DPIA. Decision: we go
with Yoti facial age estimation for the AU U16 flow. Veriff stays the documented
runner-up if Yoti's accuracy degrades in production.

AGENT: Recorded. One thing neither of us can answer today: when Yoti's estimation
confidence is below threshold, do we hard-block signup, queue for document
verification, or allow-with-restrictions? Product hasn't specified. This blocks the
fallback implementation.

DEV: Agreed, that's open — flag it as blocking and I'll raise it with product
tomorrow.
