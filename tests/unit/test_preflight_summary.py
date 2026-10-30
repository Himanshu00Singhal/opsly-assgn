from opsly.preflight import CheckResult, ready_to_build, summarize


def test_ready_to_build_ignores_implementation_skip() -> None:
    results = [
        CheckResult("runtime", "python", "pass", "ok"),
        CheckResult("implementation", "docker", "skip", "later"),
    ]
    assert ready_to_build(results)
    assert summarize(results)["pass"] == 1
