"""Canonical serialization, hashing, and safe rendering helpers."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/-]+"),
    re.compile(
        r'''(?i)((?:api[_-]?key|token|secret|password)\s*[=:]\s*)'''
        r'''(?!\[REDACTED\])[^\s,;"'}\]]+'''
    ),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
)


def jsonable(value: Any) -> Any:
    """Convert supported values into a deterministic JSON-compatible shape."""

    if isinstance(value, BaseModel):
        return jsonable(value.model_dump(mode="json", exclude_none=False))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list):
        return [jsonable(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(jsonable(item) for item in value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def stable_unique(values: Sequence[Any]) -> tuple[Any, ...]:
    seen: set[Any] = set()
    output: list[Any] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return tuple(output)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def safe_terminal_text(value: str, *, limit: int = 20_000) -> str:
    """Remove terminal-control and bidi-control characters from untrusted text."""

    value = redact_text(value)
    output: list[str] = []
    for character in value[:limit]:
        category = unicodedata.category(character)
        if character in "\n\t":
            output.append(character)
        elif category.startswith("C"):
            output.append("�")
        else:
            output.append(character)
    return "".join(output)


def markdown_code(value: str) -> str:
    return f"`{safe_terminal_text(value).replace('`', 'ˋ')}`"
