"""Versioned, deterministic Kyverno repository rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from kma.canonical import sha256_digest, stable_unique
from kma.schemas import (
    ChangeCategory,
    DependencyUpdateType,
    EvidenceSnapshot,
    RiskLevel,
    RuleMatch,
    RuleResult,
    Sha,
    StrictModel,
)

DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "config" / "kyverno-rules.v1.json"


@dataclass(frozen=True)
class Registry:
    raw: dict[str, Any]
    digest: str

    @property
    def version(self) -> str:
        return str(self.raw["registry_version"])

    @property
    def kyverno_revision(self) -> str:
        return str(self.raw["kyverno_revision"])


class _RegistryDocument(StrictModel):
    schema_version: Literal["rule-registry.v1"]
    registry_version: Annotated[str, Field(min_length=1, max_length=100)]
    kyverno_revision: Sha
    known_top_level: tuple[str, ...]
    known_root_files: tuple[str, ...]
    security_path_fragments: tuple[str, ...]
    central_dependencies: tuple[str, ...]
    known_conformance_suites: tuple[str, ...]

    @model_validator(mode="after")
    def lists_are_nonempty_and_unique(self) -> _RegistryDocument:
        collections = (
            self.known_top_level,
            self.known_root_files,
            self.security_path_fragments,
            self.central_dependencies,
            self.known_conformance_suites,
        )
        if any(not values for values in collections):
            raise ValueError("registry collections must not be empty")
        if any(len(values) != len(set(values)) for values in collections):
            raise ValueError("registry collections must not contain duplicates")
        return self


def load_registry(path: Path = DEFAULT_REGISTRY) -> Registry:
    document = _RegistryDocument.model_validate_json(path.read_text(encoding="utf-8"))
    payload = document.model_dump(mode="json")
    return Registry(payload, sha256_digest(payload))


def _file_refs(snapshot: EvidenceSnapshot, predicate: Any) -> tuple[str, ...]:
    return tuple(
        item.evidence_id
        for item in snapshot.fixture.changed_files
        if predicate(item.path, item.patch)
    )


def _match(
    rule_id: str,
    description: str,
    evidence_refs: tuple[str, ...],
    *,
    categories: tuple[ChangeCategory, ...],
    risk: RiskLevel,
    required: tuple[str, ...] = (),
    recommended: tuple[str, ...] = (),
    escalate: bool = False,
    reasons: tuple[str, ...] = (),
) -> RuleMatch:
    return RuleMatch(
        rule_id=rule_id,
        description=description,
        evidence_refs=evidence_refs,
        categories=categories,
        minimum_risk=risk,
        required_checks=required,
        recommended_checks=recommended,
        escalation_required=escalate,
        reason_codes=reasons,
    )


def _path_rules(snapshot: EvidenceSnapshot, registry: Registry) -> list[RuleMatch]:
    matches: list[RuleMatch] = []

    refs = _file_refs(snapshot, lambda path, _: path.startswith("api/"))
    if refs:
        matches.append(
            _match(
                "KYVERNO.API.CODEGEN_FANOUT",
                "API type changes fan out to generated code, clients, CRDs, charts, "
                "manifests, and docs",
                refs,
                categories=(ChangeCategory.API, ChangeCategory.GENERATED),
                risk=RiskLevel.HIGH,
                required=("codegen.all", "codegen.verify", "unit.all"),
                recommended=("docs.api-review",),
                escalate=True,
                reasons=("RULE.API_REQUIRES_CODEGEN", "RULE.API_HUMAN_REVIEW"),
            )
        )

    refs = _file_refs(
        snapshot,
        lambda path, _: (
            path.startswith(("pkg/client/", "config/crds/"))
            or path.endswith(("zz_generated.deepcopy.go", "zz_generated.register.go"))
        ),
    )
    if refs:
        matches.append(
            _match(
                "KYVERNO.GENERATED.PROVENANCE",
                "Generated surfaces require source provenance and regeneration verification",
                refs,
                categories=(ChangeCategory.GENERATED,),
                risk=RiskLevel.MEDIUM,
                required=("codegen.verify",),
                recommended=("generated.provenance-review",),
                reasons=("RULE.GENERATED_VERIFY_PROVENANCE",),
            )
        )

    refs = _file_refs(snapshot, lambda path, _: path.startswith("pkg/cel/"))
    if refs:
        matches.append(
            _match(
                "KYVERNO.CEL.BEHAVIOR",
                "CEL changes need affected package tests and behavior-level validation",
                refs,
                categories=(ChangeCategory.CEL,),
                risk=RiskLevel.MEDIUM,
                required=("unit.cel",),
                recommended=("conformance.cel",),
                reasons=("RULE.CEL_UNIT", "RULE.CEL_CONFORMANCE_CONSIDER"),
            )
        )

    refs = _file_refs(snapshot, lambda path, _: path.startswith("pkg/engine/"))
    if refs:
        matches.append(
            _match(
                "KYVERNO.ENGINE.CENTRAL",
                "Policy-engine changes affect a central evaluation path",
                refs,
                categories=(ChangeCategory.ENGINE,),
                risk=RiskLevel.HIGH,
                required=("unit.engine",),
                recommended=("conformance.relevant",),
                escalate=True,
                reasons=("RULE.ENGINE_CENTRAL",),
            )
        )

    background_refs = _file_refs(snapshot, lambda path, _: path.startswith("pkg/background/"))
    controller_refs = _file_refs(snapshot, lambda path, _: path.startswith("pkg/controllers/"))
    if background_refs or controller_refs:
        refs = stable_unique(background_refs + controller_refs)
        matches.append(
            _match(
                "KYVERNO.CONTROLLER.BEHAVIOR",
                "Background/controller changes need package and asynchronous behavior validation",
                refs,
                categories=(ChangeCategory.CONTROLLER,),
                risk=RiskLevel.MEDIUM,
                required=("unit.controllers",),
                recommended=("conformance.generating-policies",),
                reasons=("RULE.CONTROLLER_UNIT", "RULE.CONTROLLER_CONFORMANCE_CONSIDER"),
            )
        )

    cli_refs = _file_refs(
        snapshot,
        lambda path, _: path.startswith(("cmd/cli/", "pkg/cli/", "test/cli/")),
    )
    if cli_refs:
        matches.append(
            _match(
                "KYVERNO.CLI.FIXTURES",
                "CLI behavior and fixture changes require the scoped CLI test suite",
                cli_refs,
                categories=(ChangeCategory.CLI,),
                risk=RiskLevel.MEDIUM,
                required=("cli.local",),
                reasons=("RULE.CLI_LOCAL",),
            )
        )

    conformance: dict[str, list[str]] = {}
    prefix = "test/conformance/chainsaw/"
    for item in snapshot.fixture.changed_files:
        if item.path.startswith(prefix):
            remainder = item.path[len(prefix) :]
            suite = remainder.split("/", 1)[0]
            if suite:
                conformance.setdefault(suite, []).append(item.evidence_id)
    known_suites = set(registry.raw["known_conformance_suites"])
    for suite, suite_refs in sorted(conformance.items()):
        normalized = re.sub(r"[^a-z0-9.-]+", ".", suite.lower()).strip(".")
        drift = suite not in known_suites and suite not in {"_step-templates"}
        matches.append(
            _match(
                f"KYVERNO.CONFORMANCE.{normalized.upper().replace('-', '_')}",
                f"Changed Chainsaw suite {suite} should be selected directly",
                tuple(suite_refs),
                categories=(ChangeCategory.CONFORMANCE,),
                risk=RiskLevel.MEDIUM if not drift else RiskLevel.HIGH,
                required=(f"conformance.{normalized}",),
                escalate=drift,
                reasons=("RULE.CONFORMANCE_NAMED_SUITE",) if not drift else ("META.RULE_DRIFT",),
            )
        )

    workflow_refs = _file_refs(snapshot, lambda path, _: path.startswith(".github/workflows/"))
    if workflow_refs:
        privileged = _file_refs(
            snapshot,
            lambda path, patch: (
                path.startswith(".github/workflows/")
                and patch is not None
                and "pull_request_target" in patch
            ),
        )
        matches.append(
            _match(
                "KYVERNO.WORKFLOW.TRUST_BOUNDARY",
                "Workflow changes require pinned-action and privilege-boundary review",
                workflow_refs,
                categories=(ChangeCategory.WORKFLOW,),
                risk=RiskLevel.HIGH if privileged else RiskLevel.MEDIUM,
                required=("workflow.security-review", "workflow.sha-pinning"),
                escalate=bool(privileged),
                reasons=("RULE.WORKFLOW_SECURITY_REVIEW",)
                if not privileged
                else ("RULE.WORKFLOW_PRIVILEGED_TRIGGER",),
            )
        )

    security_fragments = tuple(registry.raw["security_path_fragments"])
    security_refs = _file_refs(
        snapshot,
        lambda path, _: any(fragment in path.lower() for fragment in security_fragments),
    )
    if security_refs:
        matches.append(
            _match(
                "KYVERNO.SECURITY.SENSITIVE_SURFACE",
                "Image verification, signing, or TLS changes require security review",
                security_refs,
                categories=(ChangeCategory.SECURITY,),
                risk=RiskLevel.HIGH,
                required=("human.security-review",),
                recommended=("conformance.verify-images",),
                escalate=True,
                reasons=("RULE.SECURITY_HUMAN_REVIEW",),
            )
        )

    paths = [item.path for item in snapshot.fixture.changed_files]
    docs_only = bool(paths) and all(
        path.startswith("docs/") or path.endswith(".md") for path in paths
    )
    if docs_only:
        matches.append(
            _match(
                "KYVERNO.DOCS.SCOPED",
                "Documentation-only changes should avoid unrelated runtime/conformance checks",
                tuple(item.evidence_id for item in snapshot.fixture.changed_files),
                categories=(ChangeCategory.DOCUMENTATION,),
                risk=RiskLevel.LOW,
                required=("docs.review",),
                reasons=("RULE.DOCS_AVOID_RUNTIME_TESTS",),
            )
        )

    known_roots = set(registry.raw["known_top_level"])
    known_files = set(registry.raw["known_root_files"])
    unknown_refs: list[str] = []
    for item in snapshot.fixture.changed_files:
        first = item.path.split("/", 1)[0]
        known = item.path in known_files if "/" not in item.path else first in known_roots
        if not known:
            unknown_refs.append(item.evidence_id)
    if unknown_refs:
        matches.append(
            _match(
                "KYVERNO.META.UNKNOWN_PATH",
                "One or more paths are outside the versioned repository map",
                tuple(unknown_refs),
                categories=(ChangeCategory.UNKNOWN,),
                risk=RiskLevel.HIGH,
                escalate=True,
                reasons=("META.UNKNOWN_PATH",),
            )
        )

    return matches


def _dependency_rules(snapshot: EvidenceSnapshot, registry: Registry) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    dependency_files = _file_refs(snapshot, lambda path, _: path in {"go.mod", "go.sum"})
    if dependency_files or snapshot.fixture.dependencies:
        refs = stable_unique(
            dependency_files + tuple(item.evidence_id for item in snapshot.fixture.dependencies)
        )
        baseline_required = ("dependency.review",)
        if dependency_files:
            baseline_required += ("unit.all",)
        matches.append(
            _match(
                "KYVERNO.DEPENDENCY.BASELINE",
                "Dependency changes require identity, scope, and test-impact review",
                refs,
                categories=(ChangeCategory.DEPENDENCY,),
                risk=RiskLevel.MEDIUM,
                required=baseline_required,
                reasons=("RULE.DEPENDENCY_NOT_SEMVER_ONLY",),
            )
        )

    central = set(registry.raw["central_dependencies"])
    for dependency in snapshot.fixture.dependencies:
        central_match = dependency.name in central
        elevated = (
            dependency.security_advisory
            or dependency.update_type is DependencyUpdateType.MAJOR
            or central_match
        )
        if not elevated:
            continue
        categories = [ChangeCategory.DEPENDENCY]
        if dependency.security_advisory:
            categories.append(ChangeCategory.SECURITY)
        reasons = ["RULE.DEPENDENCY_ELEVATED_REVIEW"]
        if central_match:
            reasons.append("RULE.DEPENDENCY_CENTRAL_RUNTIME")
        if dependency.security_advisory:
            reasons.append("RULE.DEPENDENCY_SECURITY_CONTEXT")
        matches.append(
            _match(
                "KYVERNO.DEPENDENCY.ELEVATED",
                f"Dependency {dependency.name} affects a central, major, or "
                "security-sensitive surface",
                (dependency.evidence_id,),
                categories=tuple(categories),
                risk=RiskLevel.HIGH,
                required=("human.dependency-review",),
                escalate=True,
                reasons=tuple(reasons),
            )
        )
    return matches


def evaluate_rules(
    snapshot: EvidenceSnapshot,
    registry: Registry | None = None,
) -> RuleResult:
    registry = registry or load_registry()
    matches = _path_rules(snapshot, registry) + _dependency_rules(snapshot, registry)

    if snapshot.contradictions or snapshot.evidence_gaps:
        refs = tuple(
            item.evidence_id for group in snapshot.fixture.evidence_groups for item in group
        )[:1]
        matches.append(
            _match(
                "KYVERNO.EVIDENCE.INCOMPLETE",
                "Missing or contradictory evidence prevents a routine conclusion",
                refs,
                categories=(ChangeCategory.UNKNOWN,),
                risk=RiskLevel.HIGH,
                escalate=True,
                reasons=stable_unique(snapshot.contradictions + ("EVIDENCE.INCOMPLETE",)),
            )
        )

    if not matches:
        matches.append(
            _match(
                "KYVERNO.META.NO_RULE_MATCH",
                "No repository rule explains the change; human classification is required",
                tuple(item.evidence_id for item in snapshot.fixture.changed_files[:1]),
                categories=(ChangeCategory.UNKNOWN,),
                risk=RiskLevel.HIGH,
                escalate=True,
                reasons=("META.NO_RULE_MATCH",),
            )
        )

    categories = stable_unique(tuple(value for item in matches for value in item.categories))
    required = stable_unique(tuple(value for item in matches for value in item.required_checks))
    recommended = stable_unique(
        tuple(value for item in matches for value in item.recommended_checks)
    )
    reasons = stable_unique(tuple(value for item in matches for value in item.reason_codes))
    return RuleResult(
        schema_version="rules.v1",
        registry_version=registry.version,
        kyverno_revision=registry.kyverno_revision,
        registry_digest=registry.digest,
        matches=tuple(matches),
        categories=categories,
        minimum_risk=RiskLevel.maximum(*(item.minimum_risk for item in matches)),
        required_checks=required,
        recommended_checks=tuple(value for value in recommended if value not in required),
        escalation_required=any(item.escalation_required for item in matches),
        reason_codes=reasons,
    )
