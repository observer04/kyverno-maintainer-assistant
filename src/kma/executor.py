"""No-network dry-run executor with revision binding and idempotency."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from kma.canonical import markdown_code, safe_terminal_text, sha256_digest
from kma.policy import CapabilityPolicy, authorization_idempotency_key
from kma.schemas import (
    AuthorizationBinding,
    DryRunOutput,
    EvidenceSnapshot,
    PlannerRecord,
    PolicyDecision,
    RuleResult,
)


class BindingError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class DryRunExecutor:
    """Renders only validated actions; no GitHub client is imported or constructed."""

    def __init__(self, state_directory: Path) -> None:
        self.state_directory = state_directory

    def execute(
        self,
        *,
        binding: AuthorizationBinding,
        snapshot: EvidenceSnapshot,
        rules: RuleResult,
        planner: PlannerRecord,
        decision: PolicyDecision,
        policy: CapabilityPolicy,
        now: datetime | None = None,
    ) -> DryRunOutput:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        self._validate_binding(binding, snapshot, rules, planner, decision, policy, now)

        self.state_directory.mkdir(parents=True, exist_ok=True)
        record_name = f"{binding.idempotency_key.removeprefix('sha256:')}.json"
        record_path = self.state_directory / record_name
        if record_path.exists():
            existing = DryRunOutput.model_validate_json(record_path.read_text(encoding="utf-8"))
            return existing.model_copy(update={"duplicate": True})

        rendered = self._render(snapshot, rules, planner, decision)
        output = DryRunOutput(
            schema_version="dry-run.v1",
            idempotency_key=binding.idempotency_key,
            rendered_markdown=rendered,
            action_count=len(decision.allowed_actions),
            duplicate=False,
        )
        temporary = record_path.with_suffix(".tmp")
        temporary.write_text(output.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(record_path)
        return output

    @staticmethod
    def _validate_binding(
        binding: AuthorizationBinding,
        snapshot: EvidenceSnapshot,
        rules: RuleResult,
        planner: PlannerRecord,
        decision: PolicyDecision,
        policy: CapabilityPolicy,
        now: datetime,
    ) -> None:
        if policy.kill_switch:
            raise BindingError("EXECUTOR.KILL_SWITCH")
        if not policy.dry_run:
            raise BindingError("EXECUTOR.DRY_RUN_DISABLED")
        if binding.subject != snapshot.fixture.subject:
            raise BindingError("EXECUTOR.SUBJECT_MISMATCH")
        if binding.evidence_digest != snapshot.evidence_digest:
            raise BindingError("EXECUTOR.EVIDENCE_DIGEST_MISMATCH")
        if binding.registry_digest != rules.registry_digest:
            raise BindingError("EXECUTOR.REGISTRY_DIGEST_MISMATCH")
        if binding.planner_digest != sha256_digest(planner):
            raise BindingError("EXECUTOR.PLANNER_DIGEST_MISMATCH")
        if binding.policy_digest != policy.digest:
            raise BindingError("EXECUTOR.POLICY_DIGEST_MISMATCH")
        if binding.decision_digest != sha256_digest(decision):
            raise BindingError("EXECUTOR.DECISION_DIGEST_MISMATCH")
        if binding.idempotency_key != authorization_idempotency_key(
            snapshot, rules, planner, decision, policy
        ):
            raise BindingError("EXECUTOR.IDEMPOTENCY_KEY_MISMATCH")
        if any(
            action.capability not in policy.allowed or action.capability in policy.denied
            for action in decision.allowed_actions
        ):
            raise BindingError("EXECUTOR.CAPABILITY_NOT_ALLOWED")
        if now < binding.issued_at:
            raise BindingError("EXECUTOR.AUTHORIZATION_NOT_YET_VALID")
        if now >= binding.expires_at:
            raise BindingError("EXECUTOR.AUTHORIZATION_EXPIRED")

    @staticmethod
    def _render(
        snapshot: EvidenceSnapshot,
        rules: RuleResult,
        planner: PlannerRecord,
        decision: PolicyDecision,
    ) -> str:
        subject = snapshot.fixture.subject
        lines = [
            "<!-- kma:dry-run; no GitHub mutation performed -->",
            "## Kyverno Maintainer Assistant — dry run",
            "",
            f"Subject: {markdown_code(subject.repo)} PR #{subject.pull_request} at "
            f"{markdown_code(subject.head_sha[:12])}",
            f"Decision: **{decision.status.value}** · Risk: **{decision.risk.value}**",
            "",
            "### Observed facts",
        ]
        for item in snapshot.fixture.changed_files:
            lines.append(f"- {markdown_code(item.path)} ({item.status.value}) [{item.evidence_id}]")
        for gap in snapshot.evidence_gaps:
            lines.append(f"- Evidence gap: {safe_terminal_text(gap)}")
        for contradiction in snapshot.contradictions:
            lines.append(f"- Contradiction: {markdown_code(contradiction)}")

        lines.extend(["", "### Deterministic Kyverno rules"])
        for match in rules.matches:
            lines.append(
                f"- {markdown_code(match.rule_id)}: {safe_terminal_text(match.description)}"
            )

        lines.extend(["", "### Model proposal"])
        if planner.proposal is None:
            lines.append(f"- No validated proposal ({planner.error_code or 'rules-only mode'})")
        else:
            lines.append(f"- {safe_terminal_text(planner.proposal.summary)}")
            if planner.proposal.uncertainty:
                lines.append(
                    "- Uncertainty: "
                    + "; ".join(safe_terminal_text(item) for item in planner.proposal.uncertainty)
                )

        if planner.agent_trace is not None:
            trace = planner.agent_trace
            lines.extend(["", "### Agent evidence trajectory"])
            lines.append(
                f"- Repository revision: {markdown_code(trace.repository_revision[:12])}"
            )
            for observation in trace.observations:
                paths = ", ".join(markdown_code(path) for path in observation.evidence_paths[:3])
                lines.append(
                    f"- {markdown_code(observation.observation_id)} "
                    f"{markdown_code(observation.tool_name)}: **{observation.status}**"
                    + (f" — {paths}" if paths else "")
                )
                if observation.validation_target is not None:
                    lines.append(
                        f"  - Validation {markdown_code(observation.validation_target)}: "
                        f"**{observation.validation_outcome}** "
                        f"(exit {observation.validation_exit_code}, network "
                        f"{markdown_code(observation.validation_network or 'unshared')})"
                    )
            lines.append(f"- Trace digest: {markdown_code(trace.trace_digest)}")

        lines.extend(["", "### Authorized recommendation"])
        lines.append(
            "- Required checks: "
            + (", ".join(markdown_code(item) for item in decision.required_checks) or "none")
        )
        lines.append(
            "- Recommended checks: "
            + (", ".join(markdown_code(item) for item in decision.recommended_checks) or "none")
        )
        escalation = "required" if decision.escalation_required else "not required"
        lines.append(f"- Human escalation: {escalation}")
        if decision.denied_actions:
            lines.append(
                "- Denied capabilities: "
                + ", ".join(
                    markdown_code(item.capability.value) for item in decision.denied_actions
                )
            )
        lines.append(
            "- Reason codes: " + ", ".join(markdown_code(item) for item in decision.reason_codes)
        )
        lines.extend(["", "_Existing CI, reviews, and branch protection remain authoritative._"])
        return "\n".join(lines)
