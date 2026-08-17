from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from kma.executor import BindingError, DryRunExecutor
from kma.policy import authorize, bind_authorization, load_policy
from kma.schemas import Capability, ProposedAction

from .conftest import analyzed


def prepared(fixture_id: str):
    snapshot, rules, planner, analysis = analyzed(fixture_id)
    policy = load_policy()
    decision = authorize(snapshot, analysis, policy)
    now = datetime(2026, 8, 12, 15, 0, tzinfo=UTC)
    binding = bind_authorization(snapshot, rules, planner, decision, policy, now=now)
    assert binding is not None
    return snapshot, rules, planner, decision, policy, binding, now


def test_executor_is_idempotent(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    executor = DryRunExecutor(tmp_path)
    first = executor.execute(
        binding=binding,
        snapshot=snapshot,
        rules=rules,
        planner=planner,
        decision=decision,
        policy=policy,
        now=now,
    )
    second = executor.execute(
        binding=binding,
        snapshot=snapshot,
        rules=rules,
        planner=planner,
        decision=decision,
        policy=policy,
        now=now,
    )
    assert not first.duplicate
    assert second.duplicate
    assert first.idempotency_key == second.idempotency_key
    assert len(list(tmp_path.glob("*.json"))) == 1


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("evidence_digest", "EXECUTOR.EVIDENCE_DIGEST_MISMATCH"),
        ("registry_digest", "EXECUTOR.REGISTRY_DIGEST_MISMATCH"),
        ("planner_digest", "EXECUTOR.PLANNER_DIGEST_MISMATCH"),
        ("policy_digest", "EXECUTOR.POLICY_DIGEST_MISMATCH"),
        ("decision_digest", "EXECUTOR.DECISION_DIGEST_MISMATCH"),
    ],
)
def test_executor_rejects_digest_mismatch(tmp_path, field: str, reason: str) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    bad = binding.model_copy(update={field: "sha256:" + "0" * 64})
    with pytest.raises(BindingError, match=reason):
        DryRunExecutor(tmp_path).execute(
            binding=bad,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=decision,
            policy=policy,
            now=now,
        )


def test_executor_rejects_stale_subject(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    stale_subject = binding.subject.model_copy(update={"head_sha": "0" * 40})
    bad = binding.model_copy(update={"subject": stale_subject})
    with pytest.raises(BindingError, match="EXECUTOR.SUBJECT_MISMATCH"):
        DryRunExecutor(tmp_path).execute(
            binding=bad,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=decision,
            policy=policy,
            now=now,
        )


def test_executor_recomputes_idempotency_key(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    bad = binding.model_copy(update={"idempotency_key": "sha256:" + "0" * 64})
    with pytest.raises(BindingError, match="EXECUTOR.IDEMPOTENCY_KEY_MISMATCH"):
        DryRunExecutor(tmp_path).execute(
            binding=bad,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=decision,
            policy=policy,
            now=now,
        )


def test_executor_binds_entire_policy_decision(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    changed = decision.model_copy(
        update={"required_checks": decision.required_checks + ("unit.all",)}
    )
    with pytest.raises(BindingError, match="EXECUTOR.DECISION_DIGEST_MISMATCH"):
        DryRunExecutor(tmp_path).execute(
            binding=binding,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=changed,
            policy=policy,
            now=now,
        )


def test_executor_rechecks_capability_policy(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, _, now = prepared("docs-only")
    forged = decision.model_copy(
        update={
            "allowed_actions": decision.allowed_actions
            + (
                ProposedAction(
                    capability=Capability.MERGE,
                    rationale="Attempt to bypass the gate",
                    evidence_refs=(),
                ),
            )
        }
    )
    forged_binding = bind_authorization(snapshot, rules, planner, forged, policy, now=now)
    assert forged_binding is not None
    with pytest.raises(BindingError, match="EXECUTOR.CAPABILITY_NOT_ALLOWED"):
        DryRunExecutor(tmp_path).execute(
            binding=forged_binding,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=forged,
            policy=policy,
            now=now,
        )


def test_executor_rejects_expired_binding(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    with pytest.raises(BindingError, match="EXECUTOR.AUTHORIZATION_EXPIRED"):
        DryRunExecutor(tmp_path).execute(
            binding=binding,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=decision,
            policy=policy,
            now=binding.expires_at + timedelta(seconds=1),
        )


def test_executor_rechecks_kill_switch(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    killed = replace(policy, kill_switch=True)
    with pytest.raises(BindingError, match="EXECUTOR.KILL_SWITCH"):
        DryRunExecutor(tmp_path).execute(
            binding=binding,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=decision,
            policy=killed,
            now=now,
        )


def test_executor_rejects_future_binding(tmp_path) -> None:
    snapshot, rules, planner, decision, policy, binding, now = prepared("docs-only")
    with pytest.raises(BindingError, match="EXECUTOR.AUTHORIZATION_NOT_YET_VALID"):
        DryRunExecutor(tmp_path).execute(
            binding=binding,
            snapshot=snapshot,
            rules=rules,
            planner=planner,
            decision=decision,
            policy=policy,
            now=now - timedelta(seconds=1),
        )
