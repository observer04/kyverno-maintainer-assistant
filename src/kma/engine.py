"""End-to-end evidence-to-audited-dry-run orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from kma import __version__
from kma.audit import AuditStore, make_run_id
from kma.evidence import build_snapshot, load_fixture
from kma.executor import BindingError, DryRunExecutor
from kma.planner import Planner, no_planner_record, run_planner
from kma.policy import authorize, bind_authorization, load_policy
from kma.reconcile import reconcile
from kma.rules import evaluate_rules, load_registry
from kma.schemas import RunRecord


def analyze_fixture(
    fixture_path: Path,
    *,
    planner: Planner | None,
    runs_directory: Path,
    now: datetime | None = None,
) -> tuple[RunRecord, Path]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    fixture = load_fixture(fixture_path)
    snapshot = build_snapshot(fixture)
    registry = load_registry()
    rules = evaluate_rules(snapshot, registry)
    planner_record = run_planner(planner, snapshot) if planner else no_planner_record()
    analysis = reconcile(snapshot, rules, planner_record)
    policy_config = load_policy()
    decision = authorize(snapshot, analysis, policy_config)
    binding = bind_authorization(
        snapshot,
        rules,
        planner_record,
        decision,
        policy_config,
        now=now,
    )
    dry_run = None
    errors: tuple[str, ...] = ()
    if binding is not None:
        executor = DryRunExecutor(runs_directory / "idempotency")
        try:
            dry_run = executor.execute(
                binding=binding,
                snapshot=snapshot,
                rules=rules,
                planner=planner_record,
                decision=decision,
                policy=policy_config,
                now=now,
            )
        except BindingError as error:
            errors = (error.reason_code,)
            binding = None

    record = RunRecord(
        schema_version="run.v1",
        run_id=make_run_id(snapshot.evidence_digest, now),
        created_at=now,
        component_version=__version__,
        snapshot=snapshot,
        rules=rules,
        planner=planner_record,
        reconciliation=analysis,
        policy=decision,
        authorization=binding,
        dry_run=dry_run,
        errors=errors,
    )
    path = AuditStore(runs_directory).save(record)
    return record, path
