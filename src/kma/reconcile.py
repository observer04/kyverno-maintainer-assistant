"""Monotonic reconciliation of deterministic rules and planner proposals."""

from __future__ import annotations

from kma.canonical import stable_unique
from kma.schemas import (
    Capability,
    EvidenceSnapshot,
    PlannerRecord,
    ProposedAction,
    ReconciledAnalysis,
    RuleResult,
)


def _valid_evidence_ids(
    snapshot: EvidenceSnapshot,
    planner: PlannerRecord | None = None,
) -> set[str]:
    identifiers = {item.evidence_id for group in snapshot.fixture.evidence_groups for item in group}
    if planner is not None and planner.agent_trace is not None:
        identifiers.update(
            item.observation_id
            for item in planner.agent_trace.observations
            if item.status == "ok"
        )
    return identifiers


def reconcile(
    snapshot: EvidenceSnapshot,
    rules: RuleResult,
    planner: PlannerRecord,
) -> ReconciledAnalysis:
    proposal = planner.proposal
    categories = list(rules.categories)
    required = list(rules.required_checks)
    recommended = list(rules.recommended_checks)
    risk = rules.minimum_risk
    escalation = rules.escalation_required
    accepted: list[str] = []
    rejected: list[str] = []
    reasons = list(rules.reason_codes)
    valid_refs = _valid_evidence_ids(snapshot, planner)

    default_ref = tuple(item.evidence_id for item in snapshot.fixture.changed_files[:1])
    actions: list[ProposedAction] = [
        ProposedAction(
            capability=Capability.RENDER_CHECK_RECOMMENDATION,
            rationale="Render the repository-grounded check recommendation",
            evidence_refs=default_ref,
        )
    ]
    if escalation:
        actions.append(
            ProposedAction(
                capability=Capability.RENDER_HUMAN_ESCALATION,
                rationale="Render the deterministic human-review requirement",
                evidence_refs=default_ref,
            )
        )

    if proposal is None:
        if planner.error_code:
            reasons.append(planner.error_code)
            accepted.append("Rules-only fallback retained all deterministic requirements")
        return ReconciledAnalysis(
            schema_version="reconciled.v1",
            categories=stable_unique(categories),
            risk=risk,
            required_checks=stable_unique(required),
            recommended_checks=tuple(
                item for item in stable_unique(recommended) if item not in required
            ),
            escalation_required=escalation,
            candidate_actions=stable_unique(actions),
            accepted_model_additions=tuple(accepted),
            rejected_model_changes=tuple(rejected),
            reason_codes=stable_unique(reasons),
        )

    categories.extend(proposal.categories)
    for check in proposal.additional_checks:
        if check not in required and check not in recommended:
            recommended.append(check)
            accepted.append(f"Model added recommended check {check}")

    if proposal.risk.rank > risk.rank:
        accepted.append(f"Model raised risk from {risk.value} to {proposal.risk.value}")
        risk = proposal.risk
    elif proposal.risk.rank < risk.rank:
        rejected.append(f"Model risk {proposal.risk.value} cannot lower rule floor {risk.value}")
        reasons.append("RECONCILE.RISK_FLOOR_PRESERVED")

    if proposal.uncertainty or proposal.open_questions:
        escalation = True
        accepted.append("Model uncertainty required human escalation")
        reasons.append("RECONCILE.MODEL_UNCERTAINTY")

    for action in proposal.proposed_actions:
        invalid = tuple(ref for ref in action.evidence_refs if ref not in valid_refs)
        if invalid:
            rejected.append(
                f"Rejected {action.capability.value}: invalid evidence refs {', '.join(invalid)}"
            )
            reasons.append("RECONCILE.INVALID_EVIDENCE_REFERENCE")
            continue
        actions.append(action)

    return ReconciledAnalysis(
        schema_version="reconciled.v1",
        categories=stable_unique(categories),
        risk=risk,
        required_checks=stable_unique(required),
        recommended_checks=tuple(
            item for item in stable_unique(recommended) if item not in required
        ),
        escalation_required=escalation,
        candidate_actions=stable_unique(actions),
        accepted_model_additions=tuple(accepted),
        rejected_model_changes=tuple(rejected),
        reason_codes=stable_unique(reasons),
    )


def model_only_reconciliation(
    snapshot: EvidenceSnapshot,
    planner: PlannerRecord,
) -> ReconciledAnalysis:
    """Evaluation-only view; it never reaches policy authorization."""

    proposal = planner.proposal
    if proposal is None:
        return ReconciledAnalysis(
            schema_version="reconciled.v1",
            categories=(),
            risk=rules_only_failure_risk(),
            required_checks=(),
            recommended_checks=(),
            escalation_required=True,
            candidate_actions=(),
            accepted_model_additions=(),
            rejected_model_changes=(),
            reason_codes=("PLANNER.UNAVAILABLE",),
        )
    valid_refs = _valid_evidence_ids(snapshot, planner)
    actions = tuple(
        action
        for action in proposal.proposed_actions
        if all(ref in valid_refs for ref in action.evidence_refs)
    )
    return ReconciledAnalysis(
        schema_version="reconciled.v1",
        categories=stable_unique(proposal.categories),
        risk=proposal.risk,
        required_checks=(),
        recommended_checks=stable_unique(proposal.additional_checks),
        escalation_required=bool(proposal.uncertainty or proposal.open_questions),
        candidate_actions=actions,
        accepted_model_additions=(),
        rejected_model_changes=(),
        reason_codes=("EVAL.MODEL_ONLY_NON_OPERATIONAL",),
    )


def rules_only_failure_risk():
    from kma.schemas import RiskLevel

    return RiskLevel.HIGH
