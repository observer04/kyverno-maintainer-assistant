"""Deny-by-default capability policy and authorization binding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from kma.canonical import sha256_digest, stable_unique
from kma.schemas import (
    AuthorizationBinding,
    Capability,
    DecisionStatus,
    EvidenceSnapshot,
    PlannerRecord,
    PolicyDecision,
    ProposedAction,
    ReconciledAnalysis,
    RuleResult,
    StrictModel,
)

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "config" / "capabilities.v1.json"


@dataclass(frozen=True)
class CapabilityPolicy:
    version: str
    dry_run: bool
    kill_switch: bool
    ttl_seconds: int
    allowed: frozenset[Capability]
    denied: frozenset[Capability]
    digest: str
    raw: dict[str, object]


class _PolicyDocument(StrictModel):
    schema_version: Literal["capability-policy.v1"]
    policy_version: Annotated[str, Field(min_length=1, max_length=100)]
    dry_run: bool
    kill_switch: bool
    authorization_ttl_seconds: Annotated[int, Field(ge=1, le=3600)]
    allowed_capabilities: tuple[Capability, ...]
    denied_capabilities: tuple[Capability, ...]

    @model_validator(mode="after")
    def capabilities_are_unique(self) -> _PolicyDocument:
        combined = self.allowed_capabilities + self.denied_capabilities
        if len(combined) != len(set(combined)):
            raise ValueError("capabilities must be classified exactly once")
        if set(combined) != set(Capability):
            raise ValueError("capability policy must classify every known capability")
        return self


def load_policy(path: Path = DEFAULT_POLICY) -> CapabilityPolicy:
    document = _PolicyDocument.model_validate_json(path.read_text(encoding="utf-8"))
    payload = document.model_dump(mode="json")
    allowed = frozenset(document.allowed_capabilities)
    denied = frozenset(document.denied_capabilities)
    return CapabilityPolicy(
        version=document.policy_version,
        dry_run=document.dry_run,
        kill_switch=document.kill_switch,
        ttl_seconds=document.authorization_ttl_seconds,
        allowed=allowed,
        denied=denied,
        digest=sha256_digest(payload),
        raw=payload,
    )


def authorization_idempotency_key(
    snapshot: EvidenceSnapshot,
    rules: RuleResult,
    planner: PlannerRecord,
    decision: PolicyDecision,
    policy: CapabilityPolicy,
) -> str:
    return sha256_digest(
        {
            "subject": snapshot.fixture.subject,
            "evidence_digest": snapshot.evidence_digest,
            "registry_digest": rules.registry_digest,
            "planner_digest": sha256_digest(planner),
            "policy_digest": policy.digest,
            "decision_digest": sha256_digest(decision),
        }
    )


def authorize(
    snapshot: EvidenceSnapshot,
    analysis: ReconciledAnalysis,
    policy: CapabilityPolicy,
) -> PolicyDecision:
    allowed: list[ProposedAction] = []
    denied: list[ProposedAction] = []
    reasons = list(analysis.reason_codes)
    escalation = analysis.escalation_required or bool(
        snapshot.contradictions or snapshot.evidence_gaps
    )

    for action in analysis.candidate_actions:
        if policy.kill_switch:
            denied.append(action)
            continue
        if policy.dry_run and action.capability in policy.allowed:
            allowed.append(action)
        else:
            denied.append(action)

    if policy.kill_switch:
        status = DecisionStatus.DENY
        reasons.append("POLICY.KILL_SWITCH")
    else:
        if denied:
            reasons.append("POLICY.FORBIDDEN_ACTION_DENIED")
            escalation = True
        if escalation:
            status = DecisionStatus.ESCALATE
        elif allowed:
            status = DecisionStatus.ALLOW_DRY_RUN
        else:
            status = DecisionStatus.DENY
            reasons.append("POLICY.NO_AUTHORIZED_ACTION")

    if snapshot.contradictions:
        reasons.append("POLICY.CONTRADICTORY_EVIDENCE")
    if snapshot.evidence_gaps:
        reasons.append("POLICY.INSUFFICIENT_EVIDENCE")

    return PolicyDecision(
        schema_version="policy-decision.v1",
        status=status,
        risk=analysis.risk,
        required_checks=analysis.required_checks,
        recommended_checks=analysis.recommended_checks,
        allowed_actions=stable_unique(allowed),
        denied_actions=stable_unique(denied),
        escalation_required=escalation,
        reason_codes=stable_unique(reasons),
    )


def bind_authorization(
    snapshot: EvidenceSnapshot,
    rules: RuleResult,
    planner: PlannerRecord,
    decision: PolicyDecision,
    policy: CapabilityPolicy,
    *,
    now: datetime | None = None,
) -> AuthorizationBinding | None:
    if not decision.allowed_actions or policy.kill_switch:
        return None
    now = (now or datetime.now(UTC)).astimezone(UTC)
    decision_digest = sha256_digest(decision)
    return AuthorizationBinding(
        schema_version="authorization.v1",
        subject=snapshot.fixture.subject,
        evidence_digest=snapshot.evidence_digest,
        registry_digest=rules.registry_digest,
        planner_digest=sha256_digest(planner),
        policy_digest=policy.digest,
        decision_digest=decision_digest,
        idempotency_key=authorization_idempotency_key(
            snapshot, rules, planner, decision, policy
        ),
        issued_at=now,
        expires_at=now + timedelta(seconds=policy.ttl_seconds),
    )
