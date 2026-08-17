from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from kma.canonical import canonical_json, redact_text, safe_terminal_text, sha256_digest
from kma.evidence import build_snapshot, load_fixture
from kma.policy import load_policy
from kma.schemas import EvidenceFixture, PlannerProposal

from .conftest import INPUTS


def test_all_fixtures_validate_and_have_stable_digests() -> None:
    for path in sorted(INPUTS.glob("*.json")):
        fixture = load_fixture(path)
        first = build_snapshot(fixture)
        second = build_snapshot(fixture)
        assert first.evidence_digest == second.evidence_digest
        assert first.evidence_digest.startswith("sha256:")


def test_snapshot_digest_ignores_evidence_collection_order() -> None:
    payload = json.loads((INPUTS / "pr-17067-cel-go.json").read_text())
    original = build_snapshot(EvidenceFixture.model_validate_json(json.dumps(payload)))
    payload["changed_files"].reverse()
    payload["dependencies"].reverse()
    reordered = build_snapshot(EvidenceFixture.model_validate_json(json.dumps(payload)))
    assert reordered.evidence_digest == original.evidence_digest


def test_fixture_rejects_extra_fields() -> None:
    payload = json.loads((INPUTS / "docs-only.json").read_text())
    payload["unexpected_authority"] = "merge"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceFixture.model_validate_json(json.dumps(payload))


def test_fixture_rejects_unsafe_path() -> None:
    payload = json.loads((INPUTS / "docs-only.json").read_text())
    payload["changed_files"][0]["path"] = "../../etc/passwd"
    with pytest.raises(ValidationError, match="normalized and relative"):
        EvidenceFixture.model_validate_json(json.dumps(payload))


def test_fixture_rejects_duplicate_evidence_ids() -> None:
    payload = json.loads((INPUTS / "pr-17067-cel-go.json").read_text())
    payload["changed_files"][1]["evidence_id"] = "file.gomod"
    with pytest.raises(ValidationError, match="must be unique"):
        EvidenceFixture.model_validate_json(json.dumps(payload))


def test_snapshot_marks_stale_check_sha() -> None:
    snapshot = build_snapshot(load_fixture(INPUTS / "stale-checks.json"))
    assert "EVIDENCE.CHECK_SHA_MISMATCH" in snapshot.contradictions


@pytest.mark.parametrize(
    "capability",
    ["force_merge", "MERGE", "merge ", "mеrge", "workflow_dispatch:anything"],
)
def test_arbitrary_capability_strings_are_rejected(capability: str) -> None:
    payload = {
        "schema_version": "planner.v1",
        "summary": "Attempt an unknown action",
        "categories": ["unknown"],
        "risk": "low",
        "additional_checks": [],
        "proposed_actions": [
            {"capability": capability, "rationale": "untrusted", "evidence_refs": []}
        ],
        "evidence_refs": [],
        "uncertainty": [],
        "open_questions": [],
    }
    with pytest.raises(ValidationError):
        PlannerProposal.model_validate(payload)


def test_canonical_json_is_order_independent_for_maps() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    assert sha256_digest({"b": 2, "a": 1}) == sha256_digest({"a": 1, "b": 2})


def test_redaction_and_terminal_safety() -> None:
    value = "token=super-secret-value\x1b[31m\u202eabc"
    rendered = safe_terminal_text(value)
    assert "super-secret-value" not in rendered
    assert "\x1b" not in rendered
    assert "\u202e" not in rendered
    assert "[REDACTED]" in redact_text(value)


def test_secret_like_fixture_text_is_redacted_before_snapshot() -> None:
    payload = json.loads((INPUTS / "docs-only.json").read_text())
    payload["body"] = "token=do-not-persist-this-value"
    payload["provenance"]["source_url"] = "https://example.test/?token=url-secret-value"
    payload["checks"] = [
        {
            "evidence_id": "check.hostile",
            "name": "token=check-secret-value\u001b[31m",
            "conclusion": "success",
            "head_sha": payload["subject"]["head_sha"],
        }
    ]
    fixture = EvidenceFixture.model_validate_json(json.dumps(payload))
    snapshot = build_snapshot(fixture)
    assert "do-not-persist-this-value" not in snapshot.fixture.body
    assert "[REDACTED]" in snapshot.fixture.body
    assert "url-secret-value" not in snapshot.fixture.provenance.source_url
    assert "check-secret-value" not in snapshot.fixture.checks[0].name
    assert "\x1b" not in snapshot.fixture.checks[0].name


def test_bare_openai_key_is_redacted() -> None:
    # Construct the synthetic value at runtime so repository secret scanners do not mistake the
    # redaction test for a committed provider credential.
    value = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz012345"
    assert value not in safe_terminal_text(value)


def test_redaction_is_idempotent_inside_json_preview() -> None:
    value = '{"text":"id-token: [REDACTED]","next":1}'
    assert redact_text(redact_text(value)) == value
    assert json.loads(redact_text(value))["next"] == 1


def test_policy_configuration_is_strict(tmp_path) -> None:
    payload = json.loads((INPUTS.parents[1] / "config" / "capabilities.v1.json").read_text())
    payload["kill_switch"] = "false"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_policy(path)
