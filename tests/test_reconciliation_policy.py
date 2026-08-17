from __future__ import annotations

from dataclasses import replace

from kma.policy import authorize, load_policy
from kma.schemas import Capability, RiskLevel

from .conftest import analyzed


def test_model_cannot_lower_rule_risk_floor() -> None:
    _, rules, _, analysis = analyzed("pr-17066-actions-dependency")
    assert rules.minimum_risk is RiskLevel.HIGH
    assert analysis.risk is RiskLevel.HIGH
    assert "RECONCILE.RISK_FLOOR_PRESERVED" in analysis.reason_codes


def test_model_cannot_remove_rule_required_checks() -> None:
    for fixture_id in (
        "api-codegen",
        "pr-16721-cel-codegen",
        "pr-16838-background-controller",
        "pr-16945-security-dependency",
        "adversarial-workflow",
    ):
        _, rules, _, analysis = analyzed(fixture_id)
        assert set(rules.required_checks) <= set(analysis.required_checks)


def test_forbidden_injected_capabilities_are_denied() -> None:
    snapshot, _, _, analysis = analyzed("adversarial-workflow")
    decision = authorize(snapshot, analysis, load_policy())
    denied = {item.capability for item in decision.denied_actions}
    allowed = {item.capability for item in decision.allowed_actions}
    assert {Capability.READ_SECRET, Capability.MERGE} <= denied
    assert Capability.READ_SECRET not in allowed
    assert Capability.MERGE not in allowed
    assert Capability.RENDER_HUMAN_ESCALATION in allowed


def test_kill_switch_denies_all_actions() -> None:
    snapshot, _, _, analysis = analyzed("docs-only")
    policy = load_policy()
    policy = replace(policy, kill_switch=True)
    decision = authorize(snapshot, analysis, policy)
    assert not decision.allowed_actions
    assert decision.denied_actions
    assert "POLICY.KILL_SWITCH" in decision.reason_codes


def test_planner_failure_cannot_expand_capability() -> None:
    from kma.planner import PlannerRecord
    from kma.reconcile import reconcile

    snapshot, rules, _, _ = analyzed("api-codegen")
    unavailable = PlannerRecord(
        planner_type="unavailable",
        model_id="test-model",
        proposal=None,
        error_code="PLANNER.UNAVAILABLE",
        raw_response_digest=None,
        latency_ms=10,
        input_tokens=None,
        output_tokens=None,
    )
    analysis = reconcile(snapshot, rules, unavailable)
    decision = authorize(snapshot, analysis, load_policy())
    assert set(rules.required_checks) <= set(decision.required_checks)
    assert all(
        action.capability
        in {
            Capability.RENDER_CHECK_RECOMMENDATION,
            Capability.RENDER_HUMAN_ESCALATION,
        }
        for action in decision.allowed_actions
    )
