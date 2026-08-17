"""Strict, versioned contracts for evidence, planning, policy, and evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=500)]
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{7,64}$")]
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
EvidenceId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")]
RuleId = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_.-]{1,127}$")]
CheckId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:/-]{0,127}$")]
ReasonCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_.-]{1,127}$")]


class StrictModel(BaseModel):
    """Base contract: no coercion surprises and no silent extra fields."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }[self]

    @classmethod
    def maximum(cls, *values: RiskLevel) -> RiskLevel:
        return max(values, key=lambda item: item.rank)


class ChangeCategory(StrEnum):
    API = "api"
    GENERATED = "generated"
    CEL = "cel"
    ENGINE = "engine"
    CONTROLLER = "controller"
    CLI = "cli"
    CONFORMANCE = "conformance"
    WORKFLOW = "workflow"
    DEPENDENCY = "dependency"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class Capability(StrEnum):
    RENDER_CHECK_RECOMMENDATION = "render_check_recommendation"
    RENDER_HUMAN_ESCALATION = "render_human_escalation"
    RENDER_LABEL_PLAN = "render_label_plan"
    DISPATCH_WORKFLOW = "dispatch_workflow"
    POST_COMMENT = "post_comment"
    UPDATE_BRANCH = "update_branch"
    READ_SECRET = "read_secret"
    PUSH = "push"
    APPROVE = "approve"
    MERGE = "merge"


class DecisionStatus(StrEnum):
    ALLOW_DRY_RUN = "allow_dry_run"
    ESCALATE = "escalate"
    DENY = "deny"


class CheckExpectation(StrEnum):
    MUST_RUN = "must_run"
    ACCEPTABLE_ALTERNATIVE = "acceptable_alternative"
    UNNECESSARY = "unnecessary"


class FileStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


class AuthorType(StrEnum):
    USER = "user"
    BOT = "bot"
    MAINTAINER = "maintainer"


class DependencyUpdateType(StrEnum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"
    UNKNOWN = "unknown"


class CheckConclusion(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    NEUTRAL = "neutral"
    ACTION_REQUIRED = "action_required"
    PENDING = "pending"


class Subject(StrictModel):
    repo: Literal["kyverno/kyverno"]
    pull_request: Annotated[int, Field(gt=0)]
    base_sha: Sha
    head_sha: Sha


class EvidenceProvenance(StrictModel):
    collected_at: datetime
    source: Literal["fixture", "github_readonly"]
    delivery_id: Annotated[str, Field(min_length=1, max_length=200)]
    source_url: Annotated[str | None, Field(max_length=1000)] = None

    @field_validator("collected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value.astimezone(UTC)


class ChangedFile(StrictModel):
    evidence_id: EvidenceId
    path: Annotated[str, Field(min_length=1, max_length=500)]
    status: FileStatus
    additions: Annotated[int, Field(ge=0)] = 0
    deletions: Annotated[int, Field(ge=0)] = 0
    previous_path: Annotated[str | None, Field(max_length=500)] = None
    patch: Annotated[str | None, Field(max_length=20_000)] = None
    patch_truncated: bool = False

    @field_validator("path", "previous_path")
    @classmethod
    def validate_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith(("/", "../")) or "/../" in value or "\x00" in value:
            raise ValueError("repository path must be normalized and relative")
        return value


class LabelEvidence(StrictModel):
    evidence_id: EvidenceId
    name: Annotated[str, Field(min_length=1, max_length=100)]
    source: Literal["github", "fixture"]


class CheckEvidence(StrictModel):
    evidence_id: EvidenceId
    name: Annotated[str, Field(min_length=1, max_length=200)]
    conclusion: CheckConclusion
    head_sha: Sha


class DependencyEvidence(StrictModel):
    evidence_id: EvidenceId
    name: Annotated[str, Field(min_length=1, max_length=300)]
    from_version: Annotated[str | None, Field(max_length=100)] = None
    to_version: Annotated[str | None, Field(max_length=100)] = None
    update_type: DependencyUpdateType = DependencyUpdateType.UNKNOWN
    direct: bool | None = None
    security_advisory: bool = False
    release_notes: Annotated[str | None, Field(max_length=10_000)] = None


class EvidenceFixture(StrictModel):
    schema_version: Literal["evidence.v1"]
    fixture_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,99}$")]
    subject: Subject
    provenance: EvidenceProvenance
    author_type: AuthorType
    dependency_bot: bool = False
    title: Annotated[str, Field(min_length=1, max_length=500)]
    body: Annotated[str, Field(max_length=20_000)] = ""
    changed_files: tuple[ChangedFile, ...]
    labels: tuple[LabelEvidence, ...] = ()
    checks: tuple[CheckEvidence, ...] = ()
    dependencies: tuple[DependencyEvidence, ...] = ()
    missing_evidence: tuple[ShortText, ...] = ()

    @model_validator(mode="after")
    def unique_evidence_ids(self) -> EvidenceFixture:
        ids = [item.evidence_id for group in self.evidence_groups for item in group]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id values must be unique within a fixture")
        return self

    @property
    def evidence_groups(self) -> tuple[tuple[Any, ...], ...]:
        return (self.changed_files, self.labels, self.checks, self.dependencies)


class EvidenceSnapshot(StrictModel):
    schema_version: Literal["snapshot.v1"]
    fixture: EvidenceFixture
    evidence_digest: Digest
    contradictions: tuple[ReasonCode, ...] = ()
    evidence_gaps: tuple[ShortText, ...] = ()


class RuleMatch(StrictModel):
    rule_id: RuleId
    description: ShortText
    evidence_refs: tuple[EvidenceId, ...]
    categories: tuple[ChangeCategory, ...] = ()
    minimum_risk: RiskLevel
    required_checks: tuple[CheckId, ...] = ()
    recommended_checks: tuple[CheckId, ...] = ()
    escalation_required: bool = False
    reason_codes: tuple[ReasonCode, ...] = ()


class RuleResult(StrictModel):
    schema_version: Literal["rules.v1"]
    registry_version: Annotated[str, Field(min_length=1, max_length=100)]
    kyverno_revision: Sha
    registry_digest: Digest
    matches: tuple[RuleMatch, ...]
    categories: tuple[ChangeCategory, ...]
    minimum_risk: RiskLevel
    required_checks: tuple[CheckId, ...]
    recommended_checks: tuple[CheckId, ...]
    escalation_required: bool
    reason_codes: tuple[ReasonCode, ...]


class ProposedAction(StrictModel):
    capability: Capability
    rationale: ShortText
    evidence_refs: tuple[EvidenceId, ...] = ()


class PlannerProposal(StrictModel):
    schema_version: Literal["planner.v1"]
    summary: Annotated[str, Field(min_length=1, max_length=1200)]
    categories: tuple[ChangeCategory, ...]
    risk: RiskLevel
    additional_checks: tuple[CheckId, ...] = ()
    proposed_actions: tuple[ProposedAction, ...] = ()
    evidence_refs: tuple[EvidenceId, ...] = ()
    uncertainty: tuple[ShortText, ...] = ()
    open_questions: tuple[ShortText, ...] = ()


class ToolObservation(StrictModel):
    """One host-observed agent tool call, without raw credentials or arguments."""

    observation_id: EvidenceId
    sequence: Annotated[int, Field(ge=1, le=100)]
    call_id: Annotated[str, Field(min_length=1, max_length=200)]
    tool_name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
    status: Literal["ok", "denied", "error"]
    arguments_digest: Digest
    result_digest: Digest
    result_preview: Annotated[str, Field(max_length=12_000)]
    repository_revision: Sha
    evidence_paths: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = ()
    bytes_returned: Annotated[int, Field(ge=0, le=100_000)] = 0
    latency_ms: Annotated[int, Field(ge=0)] = 0
    reason_code: ReasonCode | None = None
    validation_target: CheckId | None = None
    validation_outcome: Literal["passed", "failed", "timed_out"] | None = None
    validation_exit_code: int | None = None
    validation_network: Literal["unshared"] | None = None


class AgentTrace(StrictModel):
    schema_version: Literal["agent-trace.v1"]
    repository_revision: Sha
    catalog_digest: Digest
    observations: tuple[ToolObservation, ...]
    tool_call_limit: Annotated[int, Field(ge=1, le=20)]
    byte_limit: Annotated[int, Field(ge=1, le=500_000)]
    bytes_returned: Annotated[int, Field(ge=0, le=500_000)]
    budget_exhausted: bool
    trace_digest: Digest


class PlannerRecord(StrictModel):
    planner_type: Literal["fixture", "model", "agent", "unavailable", "none"]
    transport: Literal["fixture", "local-proxy", "openai", "openrouter"] | None = None
    model_id: Annotated[str | None, Field(max_length=200)] = None
    proposal: PlannerProposal | None = None
    agent_trace: AgentTrace | None = None
    error_code: ReasonCode | None = None
    raw_response_digest: Digest | None = None
    latency_ms: Annotated[int, Field(ge=0)] = 0
    input_tokens: Annotated[int | None, Field(ge=0)] = None
    output_tokens: Annotated[int | None, Field(ge=0)] = None


class ReconciledAnalysis(StrictModel):
    schema_version: Literal["reconciled.v1"]
    categories: tuple[ChangeCategory, ...]
    risk: RiskLevel
    required_checks: tuple[CheckId, ...]
    recommended_checks: tuple[CheckId, ...]
    escalation_required: bool
    candidate_actions: tuple[ProposedAction, ...]
    accepted_model_additions: tuple[ShortText, ...] = ()
    rejected_model_changes: tuple[ShortText, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()


class PolicyDecision(StrictModel):
    schema_version: Literal["policy-decision.v1"]
    status: DecisionStatus
    risk: RiskLevel
    required_checks: tuple[CheckId, ...]
    recommended_checks: tuple[CheckId, ...]
    allowed_actions: tuple[ProposedAction, ...]
    denied_actions: tuple[ProposedAction, ...]
    escalation_required: bool
    reason_codes: tuple[ReasonCode, ...]


class AuthorizationBinding(StrictModel):
    schema_version: Literal["authorization.v1"]
    subject: Subject
    evidence_digest: Digest
    registry_digest: Digest
    planner_digest: Digest
    policy_digest: Digest
    decision_digest: Digest
    idempotency_key: Digest
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def expiry_follows_issue(self) -> AuthorizationBinding:
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("authorization timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("authorization expires_at must follow issued_at")
        return self


class DryRunOutput(StrictModel):
    schema_version: Literal["dry-run.v1"]
    idempotency_key: Digest
    rendered_markdown: Annotated[str, Field(max_length=20_000)]
    action_count: Annotated[int, Field(ge=0)]
    duplicate: bool = False


class RunRecord(StrictModel):
    schema_version: Literal["run.v1"]
    run_id: Annotated[str, Field(pattern=r"^run_[0-9a-f]{16}$")]
    created_at: datetime
    component_version: ShortText
    snapshot: EvidenceSnapshot
    rules: RuleResult
    planner: PlannerRecord
    reconciliation: ReconciledAnalysis
    policy: PolicyDecision
    authorization: AuthorizationBinding | None = None
    dry_run: DryRunOutput | None = None
    errors: tuple[ReasonCode, ...] = ()


class CheckAnnotation(StrictModel):
    check_id: CheckId
    expectation: CheckExpectation
    alternative_group: Annotated[str | None, Field(max_length=100)] = None
    rationale: ShortText


class CaseAnnotation(StrictModel):
    schema_version: Literal["annotation.v1"]
    case_id: Annotated[str, Field(pattern=r"^C[0-9]{2}[a-z0-9_.-]*$")]
    fixture_id: Annotated[str, Field(min_length=1, max_length=100)]
    source: Literal["applicant_annotation", "maintainer_confirmed"]
    annotation_date: datetime
    categories: tuple[ChangeCategory, ...]
    minimum_risk: RiskLevel
    checks: tuple[CheckAnnotation, ...]
    forbidden_actions: tuple[Capability, ...]
    escalation_required: bool
    expected_rule_ids: tuple[RuleId, ...] = ()
    uncertainty: tuple[ShortText, ...] = ()

    @field_validator("annotation_date")
    @classmethod
    def annotation_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("annotation_date must be timezone-aware")
        return value.astimezone(UTC)


class VariantCaseResult(StrictModel):
    case_id: str
    fixture_id: str
    variant: Literal["rules_only", "model_only", "hybrid"]
    selected_checks: tuple[CheckId, ...]
    missing_must_run: tuple[CheckId, ...]
    avoidable_checks: tuple[CheckId, ...]
    risk: RiskLevel
    escalation: bool
    escalation_correct: bool
    unsafe_actions: tuple[Capability, ...]
    false_reassurance: bool
    rule_ids: tuple[RuleId, ...]


class EvaluationReport(StrictModel):
    schema_version: Literal["evaluation.v1"]
    generated_at: datetime
    planner_type: Literal["fixture", "model", "agent"]
    case_results: tuple[VariantCaseResult, ...]
    metrics: dict[str, dict[str, int | float]]
    invariant_results: dict[str, bool]
    limitations: tuple[str, ...]
