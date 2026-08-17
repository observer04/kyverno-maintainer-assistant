from __future__ import annotations

import pytest

from kma.evaluation import load_annotation
from kma.schemas import RiskLevel

from .conftest import ANNOTATIONS, analyzed


def test_every_annotation_expected_rule_is_observed() -> None:
    for annotation_path in sorted(ANNOTATIONS.glob("*.json")):
        annotation = load_annotation(annotation_path)
        _, rules, _, _ = analyzed(annotation.fixture_id)
        assert set(annotation.expected_rule_ids) <= {item.rule_id for item in rules.matches}


@pytest.mark.parametrize(
    ("fixture_id", "rule_ids", "required_checks", "risk", "escalation"),
    [
        (
            "api-codegen",
            {"KYVERNO.API.CODEGEN_FANOUT", "KYVERNO.GENERATED.PROVENANCE"},
            {"codegen.all", "codegen.verify", "unit.all"},
            RiskLevel.HIGH,
            True,
        ),
        (
            "pr-16721-cel-codegen",
            {"KYVERNO.CEL.BEHAVIOR", "KYVERNO.GENERATED.PROVENANCE", "KYVERNO.CONFORMANCE.CEL"},
            {"unit.cel", "codegen.verify", "conformance.cel"},
            RiskLevel.MEDIUM,
            False,
        ),
        (
            "pr-16838-background-controller",
            {"KYVERNO.CONTROLLER.BEHAVIOR", "KYVERNO.CONFORMANCE.GENERATING_POLICIES"},
            {"unit.controllers", "conformance.generating-policies"},
            RiskLevel.MEDIUM,
            False,
        ),
        (
            "docs-only",
            {"KYVERNO.DOCS.SCOPED"},
            {"docs.review"},
            RiskLevel.LOW,
            False,
        ),
    ],
)
def test_repository_rules(
    fixture_id: str,
    rule_ids: set[str],
    required_checks: set[str],
    risk: RiskLevel,
    escalation: bool,
) -> None:
    _, rules, _, _ = analyzed(fixture_id)
    assert rule_ids <= {item.rule_id for item in rules.matches}
    assert required_checks <= set(rules.required_checks)
    assert rules.minimum_risk is risk
    assert rules.escalation_required is escalation


def test_workflow_dependency_avoids_unrelated_unit_suite() -> None:
    _, rules, _, _ = analyzed("pr-17066-actions-dependency")
    assert "workflow.security-review" in rules.required_checks
    assert "human.dependency-review" in rules.required_checks
    assert "unit.all" not in rules.required_checks
    assert not any(check.startswith("conformance.") for check in rules.required_checks)


def test_security_patch_dependency_is_not_routine() -> None:
    _, rules, _, _ = analyzed("pr-16945-security-dependency")
    assert rules.minimum_risk is RiskLevel.HIGH
    assert rules.escalation_required
    assert "human.dependency-review" in rules.required_checks


def test_stale_check_adds_incomplete_evidence_rule() -> None:
    _, rules, _, _ = analyzed("stale-checks")
    assert "KYVERNO.EVIDENCE.INCOMPLETE" in {item.rule_id for item in rules.matches}
    assert "EVIDENCE.CHECK_SHA_MISMATCH" in rules.reason_codes
