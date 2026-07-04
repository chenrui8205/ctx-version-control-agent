"""Golden scenarios S1/S2 in fake mode (§12.3) — runs in CI on every change."""


def test_s1_mixed_second_session(session):
    from evals.scenario_lib import run_s1

    r = run_s1(session, "fake")
    failures = [f"{c.name}: {c.detail}" for c in r.checks if not c.ok]
    assert r.passed, failures


def test_s2_close_the_loop(session):
    from evals.scenario_lib import run_s2

    r = run_s2(session, "fake")
    failures = [f"{c.name}: {c.detail}" for c in r.checks if not c.ok]
    assert r.passed, failures
