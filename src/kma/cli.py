"""Command-line interface for analysis, attacks, evaluation, and audit explanation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from kma.audit import AuditStore
from kma.engine import analyze_fixture
from kma.evaluation import format_report, run_evaluation
from kma.evidence import load_fixture
from kma.planner import (
    OPENROUTER_RESPONSES_URL,
    FixturePlanner,
    OpenAIPlanner,
    ResponsesToolPlanner,
)
from kma.repository_tools import RepositoryToolHost

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = ROOT / "fixtures" / "inputs"
DEFAULT_ANNOTATIONS = ROOT / "fixtures" / "annotations"
DEFAULT_RUNS = ROOT / "runs"
DEFAULT_REPORTS = ROOT / "reports"


def _transport(
    transport: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    transport = transport or os.environ.get("KMA_TRANSPORT", "local-proxy")
    if transport == "local-proxy":
        return (
            os.environ.get("KMA_PROXY_URL", "http://127.0.0.1:8317/v1"),
            os.environ.get("KMA_PROXY_TOKEN", "local-proxy"),
            None,
        )
    if transport == "openai":
        return None, os.environ.get("OPENAI_API_KEY"), None
    if transport == "openrouter":
        return OPENROUTER_RESPONSES_URL, os.environ.get("OPENROUTER_API_KEY"), "openrouter"
    raise ValueError("KMA_TRANSPORT must be local-proxy, openai, or openrouter")


def _planner(
    name: str,
    model: str | None = None,
    *,
    repository: Path | None = None,
    expected_revision: str | None = None,
    transport: str | None = None,
):
    if name == "none":
        return None
    if name == "fixture":
        return FixturePlanner()
    if name in {"model", "snapshot"}:
        model_id = model or os.environ.get("KMA_MODEL")
        if not model_id:
            raise ValueError("--model or KMA_MODEL is required for a model planner")
        base_url, api_key, remote_provider = _transport(transport)
        return OpenAIPlanner(
            model_id,
            base_url=base_url,
            api_key=api_key,
            remote_provider=remote_provider,
        )
    if name == "agent":
        model_id = model or os.environ.get("KMA_MODEL")
        if not model_id:
            raise ValueError("--model or KMA_MODEL is required for planner=agent")
        if repository is None or expected_revision is None:
            raise ValueError("planner=agent requires a pinned --repo checkout")
        base_url, api_key, remote_provider = _transport(transport)
        return ResponsesToolPlanner(
            model_id,
            repository_root=repository,
            expected_revision=expected_revision,
            base_url=base_url,
            api_key=api_key,
            remote_provider=remote_provider,
        )
    raise ValueError(f"unknown planner {name}")


def _print_run(record, audit_path: Path) -> None:
    subject = record.snapshot.fixture.subject
    print("Kyverno Maintainer Assistant — DRY RUN")
    print(f"run: {record.run_id}")
    print(f"subject: {subject.repo}#{subject.pull_request}@{subject.head_sha[:12]}")
    print(f"evidence: {record.snapshot.evidence_digest}")
    print(f"decision: {record.policy.status.value} risk={record.policy.risk.value}")
    print(f"required: {', '.join(record.policy.required_checks) or 'none'}")
    print(f"recommended: {', '.join(record.policy.recommended_checks) or 'none'}")
    print(f"escalation: {'required' if record.policy.escalation_required else 'not required'}")
    if record.policy.denied_actions:
        print(
            "denied: "
            + ", ".join(action.capability.value for action in record.policy.denied_actions)
        )
    print("rules: " + ", ".join(match.rule_id for match in record.rules.matches))
    print(f"planner: {record.planner.planner_type}")
    if record.planner.transport is not None:
        print(f"transport: {record.planner.transport}")
    if record.planner.error_code is not None:
        print(f"planner-error: {record.planner.error_code}")
    if record.planner.agent_trace is not None:
        trace = record.planner.agent_trace
        print(
            f"agent-trace: {len(trace.observations)} evidence calls · "
            f"{trace.bytes_returned} bytes · {trace.trace_digest}"
        )
        for observation in trace.observations:
            paths = ", ".join(observation.evidence_paths[:3]) or "none"
            print(
                f"  [{observation.observation_id}] {observation.tool_name} "
                f"{observation.status} paths={paths}"
            )
            if observation.validation_target is not None:
                print(
                    f"    validation: {observation.validation_target} "
                    f"outcome={observation.validation_outcome} "
                    f"exit={observation.validation_exit_code} "
                    f"network={observation.validation_network}"
                )
    print(f"audit: {audit_path}")
    if record.dry_run:
        print("\n" + record.dry_run.rendered_markdown)


def _add_planner_arguments(parser: argparse.ArgumentParser, *, allow_none: bool = True) -> None:
    choices = ["fixture", "snapshot", "agent", "model"]
    if allow_none:
        choices.insert(0, "none")
    parser.add_argument("--planner", choices=choices, default="fixture")
    parser.add_argument("--model", help="Model ID for --planner snapshot/agent")
    parser.add_argument(
        "--repo",
        type=Path,
        help="Clean Kyverno checkout pinned to the fixture head SHA (required for agent)",
    )
    parser.add_argument(
        "--transport",
        choices=("local-proxy", "openai", "openrouter"),
        default=os.environ.get("KMA_TRANSPORT", "local-proxy"),
        help=(
            "Model transport; local-proxy is loopback-only, openai uses OPENAI_API_KEY, and "
            "openrouter uses OPENROUTER_API_KEY"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kma",
        description="Kyverno Maintainer Assistant: revision-bound dry-run analysis",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze-pr", help="Analyze a saved PR fixture")
    analyze.add_argument("--fixture", type=Path, required=True)
    analyze.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    _add_planner_arguments(analyze)

    attack = subparsers.add_parser("replay-attack", help="Replay an adversarial fixture")
    attack.add_argument("--fixture", type=Path, required=True)
    attack.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    _add_planner_arguments(attack)

    evaluate = subparsers.add_parser("eval", help="Compare rules/model/hybrid variants")
    evaluate.add_argument("--cases", type=Path, default=DEFAULT_INPUTS)
    evaluate.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    evaluate.add_argument("--output", type=Path, default=DEFAULT_REPORTS / "evaluation.json")
    _add_planner_arguments(evaluate, allow_none=False)

    explain = subparsers.add_parser("explain-run", help="Explain an audited run")
    explain.add_argument("--run-id", required=True)
    explain.add_argument("--runs", type=Path, default=DEFAULT_RUNS)

    schema = subparsers.add_parser("export-schemas", help="Export contract JSON schemas")
    schema.add_argument("--output", type=Path, required=True)

    doctor = subparsers.add_parser(
        "agent-doctor",
        help="Verify the pinned checkout, validation catalog, and model transport",
    )
    doctor.add_argument("--fixture", type=Path, required=True)
    doctor.add_argument("--repo", type=Path, required=True)
    doctor.add_argument("--model", help="Expected model ID; defaults to KMA_MODEL")
    doctor.add_argument(
        "--transport",
        choices=("local-proxy", "openai", "openrouter"),
        default=os.environ.get("KMA_TRANSPORT", "local-proxy"),
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.command in {"analyze-pr", "replay-attack"}:
        fixture = load_fixture(args.fixture)
        planner = _planner(
            args.planner,
            args.model,
            repository=args.repo,
            expected_revision=fixture.subject.head_sha,
            transport=args.transport,
        )
        record, path = analyze_fixture(
            args.fixture,
            planner=planner,
            runs_directory=args.runs,
        )
        _print_run(record, path)
        requested_live_model = args.planner in {"snapshot", "model", "agent"}
        planner_unavailable = record.planner.planner_type == "unavailable"
        return 0 if not record.errors and not (requested_live_model and planner_unavailable) else 2

    if args.command == "eval":
        if args.planner == "agent":
            raise ValueError("live agent evaluation requires per-case pinned checkouts")
        planner = _planner(args.planner, args.model, transport=args.transport)
        if planner is None:
            raise ValueError("evaluation requires fixture or model planner")
        report = run_evaluation(
            fixtures_directory=args.cases,
            annotations_directory=args.annotations,
            planner=planner,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(format_report(report))
        print(f"\nreport: {args.output}")
        return 0

    if args.command == "explain-run":
        record = AuditStore(args.runs).load(args.run_id)
        print(record.model_dump_json(indent=2))
        return 0

    if args.command == "export-schemas":
        from kma.schemas import (
            AgentTrace,
            CaseAnnotation,
            EvaluationReport,
            EvidenceFixture,
            PlannerProposal,
            RunRecord,
        )

        args.output.mkdir(parents=True, exist_ok=True)
        for model in (
            EvidenceFixture,
            PlannerProposal,
            AgentTrace,
            RunRecord,
            CaseAnnotation,
            EvaluationReport,
        ):
            path = args.output / f"{model.__name__}.schema.json"
            path.write_text(json.dumps(model.model_json_schema(), indent=2), encoding="utf-8")
            print(path)
        return 0

    if args.command == "agent-doctor":
        fixture = load_fixture(args.fixture)
        host = RepositoryToolHost(
            args.repo,
            expected_revision=fixture.subject.head_sha,
        )
        traversal_probe = host.execute(
            "read_repository_file",
            json.dumps({"path": "../outside", "start_line": 1, "end_line": 1}),
            "doctor-path-boundary",
        )
        shell_probe = host.execute(
            "run_shell",
            json.dumps({"command": "git push"}),
            "doctor-capability-boundary",
        )
        if traversal_probe["status"] != "denied" or shell_probe["status"] != "denied":
            raise ValueError("tool-boundary self-test failed")
        planner = _planner(
            "agent",
            args.model,
            repository=args.repo,
            expected_revision=fixture.subject.head_sha,
            transport=args.transport,
        )
        models = planner.available_models()
        print("Kyverno Maintainer Assistant — agent doctor")
        print(f"repository: ok {host.repository_revision}")
        print(f"catalog: ok {host.catalog.catalog_version} {host.catalog_digest}")
        print("tool-boundary: ok traversal denied")
        print("tool-boundary: ok arbitrary shell unavailable")
        readiness = host.validation_readiness()
        print(
            "validation-sandbox: ok "
            f"{readiness['backend']} network={readiness['network']} "
            f"source={readiness['source_mount']} go={readiness['go_version']}"
        )
        print(f"transport: ok {args.transport}")
        print(f"models: {', '.join(models) or 'none returned'}")
        if planner.model_id not in models:
            raise ValueError(f"configured model is not advertised: {planner.model_id}")
        print(f"selected-model: ok {planner.model_id}")
        return 0
    raise AssertionError(f"unhandled command {args.command}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    try:
        code = _run(parser.parse_args(argv))
    except (OSError, ValueError, ValidationError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
