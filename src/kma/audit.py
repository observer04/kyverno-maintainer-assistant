"""Append-only local JSON run records."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from kma.canonical import sha256_digest
from kma.schemas import RunRecord


class AuditStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def save(self, record: RunRecord) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{record.run_id}.json"
        with target.open("x", encoding="utf-8") as stream:
            stream.write(record.model_dump_json(indent=2))
        return target

    def load(self, run_id: str) -> RunRecord:
        if re.fullmatch(r"run_[0-9a-f]{16}", run_id) is None:
            raise ValueError("invalid run ID")
        path = self.directory / f"{run_id}.json"
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def make_run_id(evidence_digest: str, created_at: datetime | None = None) -> str:
    created_at = (created_at or datetime.now(UTC)).astimezone(UTC)
    digest = sha256_digest({"evidence_digest": evidence_digest, "created_at": created_at})
    return f"run_{digest.removeprefix('sha256:')[:16]}"
