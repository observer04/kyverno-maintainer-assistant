"""Fixture ingestion and immutable evidence-snapshot construction."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from kma.canonical import safe_terminal_text, sha256_digest, stable_unique
from kma.schemas import EvidenceFixture, EvidenceSnapshot


class EvidenceLoadError(ValueError):
    """Raised when an input cannot cross the strict evidence boundary."""


def load_fixture(path: Path) -> EvidenceFixture:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as error:
        raise EvidenceLoadError(f"unable to read fixture {path}: {error}") from error
    try:
        return EvidenceFixture.model_validate_json(payload)
    except ValidationError as error:
        raise EvidenceLoadError(f"invalid evidence fixture {path}: {error}") from error


def build_snapshot(fixture: EvidenceFixture) -> EvidenceSnapshot:
    fixture = _sanitize_fixture(fixture)
    contradictions: list[str] = []
    gaps = list(fixture.missing_evidence)

    if fixture.subject.base_sha == fixture.subject.head_sha:
        contradictions.append("EVIDENCE.BASE_EQUALS_HEAD")
    if not fixture.changed_files:
        gaps.append("No changed-file evidence was collected")
    if any(item.patch_truncated for item in fixture.changed_files):
        gaps.append("One or more patch excerpts are truncated")
    if any(check.head_sha != fixture.subject.head_sha for check in fixture.checks):
        contradictions.append("EVIDENCE.CHECK_SHA_MISMATCH")

    digest = sha256_digest(
        {
            "schema_version": fixture.schema_version,
            "fixture": fixture,
        }
    )
    return EvidenceSnapshot(
        schema_version="snapshot.v1",
        fixture=fixture,
        evidence_digest=digest,
        contradictions=stable_unique(contradictions),
        evidence_gaps=stable_unique(gaps),
    )


def _sanitize_fixture(fixture: EvidenceFixture) -> EvidenceFixture:
    """Redact unsafe text and normalize order before persistence, hashing, or planning."""

    changed_files = tuple(
        sorted(
            (
                item.model_copy(
                    update={
                        "path": safe_terminal_text(item.path, limit=500),
                        "previous_path": (
                            safe_terminal_text(item.previous_path, limit=500)
                            if item.previous_path is not None
                            else None
                        ),
                        "patch": (
                            safe_terminal_text(item.patch, limit=20_000)
                            if item.patch is not None
                            else None
                        ),
                    }
                )
                for item in fixture.changed_files
            ),
            key=lambda item: item.evidence_id,
        )
    )
    labels = tuple(
        sorted(
            (
                item.model_copy(update={"name": safe_terminal_text(item.name, limit=100)})
                for item in fixture.labels
            ),
            key=lambda item: item.evidence_id,
        )
    )
    checks = tuple(
        sorted(
            (
                item.model_copy(update={"name": safe_terminal_text(item.name, limit=200)})
                for item in fixture.checks
            ),
            key=lambda item: item.evidence_id,
        )
    )
    dependencies = tuple(
        sorted(
            (
                item.model_copy(
                    update={
                        "name": safe_terminal_text(item.name, limit=300),
                        "from_version": (
                            safe_terminal_text(item.from_version, limit=100)
                            if item.from_version is not None
                            else None
                        ),
                        "to_version": (
                            safe_terminal_text(item.to_version, limit=100)
                            if item.to_version is not None
                            else None
                        ),
                        "release_notes": (
                            safe_terminal_text(item.release_notes, limit=10_000)
                            if item.release_notes is not None
                            else None
                        ),
                    }
                )
                for item in fixture.dependencies
            ),
            key=lambda item: item.evidence_id,
        )
    )
    provenance = fixture.provenance.model_copy(
        update={
            "delivery_id": safe_terminal_text(fixture.provenance.delivery_id, limit=200),
            "source_url": (
                safe_terminal_text(fixture.provenance.source_url, limit=1000)
                if fixture.provenance.source_url is not None
                else None
            ),
        }
    )
    return fixture.model_copy(
        update={
            "provenance": provenance,
            "title": safe_terminal_text(fixture.title, limit=500),
            "body": safe_terminal_text(fixture.body, limit=20_000),
            "changed_files": changed_files,
            "labels": labels,
            "checks": checks,
            "dependencies": dependencies,
            "missing_evidence": tuple(
                sorted({safe_terminal_text(item, limit=500) for item in fixture.missing_evidence})
            ),
        }
    )
