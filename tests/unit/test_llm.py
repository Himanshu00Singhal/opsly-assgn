from opsly.shared.llm import analyze_query_rules, route_to_agents_rules


def test_analyze_query_intent() -> None:
    out = analyze_query_rules("Explain how Depends works")
    assert out["intent"] == "explain"
    assert "Depends" in out["entities"]


def test_route_plan_includes_graph() -> None:
    analysis = analyze_query_rules("What classes inherit from APIRouter?")
    plan = route_to_agents_rules(analysis)
    assert plan["parallel"]
