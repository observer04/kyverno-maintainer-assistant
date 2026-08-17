from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from kma.evidence import build_snapshot, load_fixture
from kma.planner import (
    OpenAIPlanner,
    ResponsesToolPlanner,
    _OpenAIPlannerResponse,
    _validate_loopback_responses_url,
    _validate_responses_base_url,
    run_planner,
)
from kma.schemas import Capability, ChangeCategory, RiskLevel

from .conftest import INPUTS
from .test_repository_tools import PassingValidationRunner, make_repository


class _FakeResponses:
    def __init__(self) -> None:
        self.arguments = None

    def parse(self, **kwargs):
        self.arguments = kwargs
        parsed = SimpleNamespace(
            summary="CEL behavior and stale evidence need review",
            categories=[ChangeCategory.CEL],
            risk=RiskLevel.HIGH,
            additional_checks=["conformance.cel"],
            proposed_actions=[
                SimpleNamespace(
                    capability=Capability.RENDER_HUMAN_ESCALATION,
                    rationale="Surface the evidence contradiction",
                    evidence_refs=["file.gomod"],
                )
            ],
            evidence_refs=["file.gomod"],
            uncertainty=["The recorded check belongs to a stale head"],
            open_questions=[],
        )
        usage = SimpleNamespace(input_tokens=123, output_tokens=45)
        return SimpleNamespace(output_parsed=parsed, usage=usage)


def test_openai_adapter_sends_full_snapshot_and_parses_contract() -> None:
    snapshot = build_snapshot(load_fixture(INPUTS / "stale-checks.json"))
    responses = _FakeResponses()
    planner = object.__new__(OpenAIPlanner)
    planner.model_id = "test-model"
    planner._client = SimpleNamespace(responses=responses)

    proposal, metadata = planner.propose(snapshot)

    assert proposal.risk is RiskLevel.HIGH
    assert proposal.proposed_actions[0].capability is Capability.RENDER_HUMAN_ESCALATION
    assert metadata["input_tokens"] == 123
    user_payload = json.loads(responses.arguments["input"][1]["content"])
    assert user_payload["snapshot"]["contradictions"] == ["EVIDENCE.CHECK_SHA_MISMATCH"]
    assert "proposal_capability_vocabulary" in user_payload
    assert "allowed_output_capabilities" not in user_payload
    assert "tools" not in responses.arguments
    assert responses.arguments["store"] is False


def test_planner_exception_falls_back_without_error_text() -> None:
    class BrokenPlanner:
        planner_type = "model"
        model_id = "test-model"

        def propose(self, snapshot):
            raise RuntimeError("token=must-not-leak")

    snapshot = build_snapshot(load_fixture(INPUTS / "docs-only.json"))
    record = run_planner(BrokenPlanner(), snapshot)
    assert record.planner_type == "unavailable"
    assert record.error_code == "PLANNER.UNAVAILABLE"
    assert "must-not-leak" not in record.model_dump_json()


class _AgentResponses:
    def __init__(self) -> None:
        self.calls = []
        self.outputs = [
            [
                SimpleNamespace(
                    type="function_call",
                    name="lookup_validation_targets",
                    call_id="call-1",
                    arguments=json.dumps({"changed_paths": ["go.mod"]}),
                )
            ],
            [
                SimpleNamespace(
                    type="function_call",
                    name="search_repository",
                    call_id="call-2",
                    arguments=json.dumps(
                        {
                            "query": "github.com/google/cel-go",
                            "paths": ["pkg/cel"],
                            "max_results": 5,
                        }
                    ),
                )
            ],
            [
                SimpleNamespace(
                    type="function_call",
                    name="run_validation_target",
                    call_id="call-3",
                    arguments=json.dumps({"target_id": "unit.cel.compiler"}),
                )
            ],
            [
                SimpleNamespace(
                    type="function_call",
                    name="submit_maintainer_plan",
                    call_id="call-4",
                    arguments=json.dumps(
                        {
                            "summary": "cel-go reaches Kyverno CEL compiler code",
                            "categories": ["dependency", "cel"],
                            "risk": "high",
                            "additional_checks": ["unit.all", "unit.cel"],
                            "proposed_actions": [
                                {
                                    "capability": "render_check_recommendation",
                                    "rationale": "Show the scoped validation plan",
                                    "evidence_refs": ["tool.0002"],
                                }
                            ],
                            "evidence_refs": [
                                "file.gomod",
                                "tool.0001",
                                "tool.0002",
                                "tool.0003",
                            ],
                            "uncertainty": [],
                            "open_questions": [],
                        }
                    ),
                )
            ],
        ]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        return SimpleNamespace(output=output, usage=usage)


def test_responses_tool_planner_executes_host_tools_and_records_trace(tmp_path) -> None:
    root, revision = make_repository(tmp_path)
    fixture = load_fixture(INPUTS / "pr-17067-cel-go.json")
    fixture = fixture.model_copy(
        update={"subject": fixture.subject.model_copy(update={"head_sha": revision})}
    )
    snapshot = build_snapshot(fixture)
    responses = _AgentResponses()
    planner = ResponsesToolPlanner(
        "test-model",
        repository_root=root,
        expected_revision=revision,
        client=SimpleNamespace(responses=responses),
        validation_runner=PassingValidationRunner(),
    )

    record = run_planner(planner, snapshot)

    assert record.planner_type == "agent"
    assert record.proposal is not None
    assert record.agent_trace is not None
    assert [item.tool_name for item in record.agent_trace.observations] == [
        "lookup_validation_targets",
        "search_repository",
        "run_validation_target",
    ]
    assert record.proposal.evidence_refs[-1] == "tool.0003"
    assert record.input_tokens == 40
    assert all(call["store"] is False for call in responses.calls)
    assert any(
        tool["name"] == "search_repository" for tool in responses.calls[0]["tools"]
    )
    assert {tool["name"] for tool in responses.calls[-1]["tools"]} == {
        "submit_maintainer_plan"
    }
    submission = responses.calls[-1]["tools"][0]
    allowed_refs = submission["parameters"]["properties"]["evidence_refs"]["items"][
        "enum"
    ]
    assert "file.gomod" in allowed_refs
    assert "tool.0003" in allowed_refs
    assert "function_call_output" in {
        item["type"]
        for item in responses.calls[1]["input"]
        if isinstance(item, dict) and "type" in item
    }


def test_local_proxy_url_is_explicitly_loopback_only() -> None:
    assert (
        _validate_loopback_responses_url("http://127.0.0.1:8317/v1")
        == "http://127.0.0.1:8317/v1"
    )
    for value in (
        "https://127.0.0.1:8317/v1",
        "http://localhost:8317/v1",
        "http://127.0.0.1:8317/v1?token=secret",
        "http://127.0.0.1:8317/other",
        "http://example.com:8317/v1",
    ):
        try:
            _validate_loopback_responses_url(value)
        except ValueError:
            continue
        raise AssertionError(f"unsafe local proxy URL accepted: {value}")
    assert (
        _validate_responses_base_url(
            "https://openrouter.ai/api/v1",
            remote_provider="openrouter",
        )
        == "https://openrouter.ai/api/v1"
    )
    with pytest.raises(ValueError, match="fixed HTTPS"):
        _validate_responses_base_url(
            "https://attacker.invalid/v1",
            remote_provider="openrouter",
        )


def test_model_discovery_failure_is_sanitized() -> None:
    class BrokenModels:
        def list(self):
            raise RuntimeError("api_key=must-not-leak")

    planner = object.__new__(ResponsesToolPlanner)
    planner._client = SimpleNamespace(models=BrokenModels())

    with pytest.raises(RuntimeError, match=r"^PLANNER\.TRANSPORT_UNAVAILABLE$") as captured:
        planner.available_models()
    assert "must-not-leak" not in str(captured.value)


def test_agent_submission_check_ids_use_a_closed_vocabulary() -> None:
    payload = {
        "summary": "Dependency review",
        "categories": ["dependency"],
        "risk": "high",
        "additional_checks": ["run all relevant tests"],
        "proposed_actions": [],
        "evidence_refs": ["tool.0001"],
        "uncertainty": [],
        "open_questions": [],
    }

    with pytest.raises(ValidationError):
        _OpenAIPlannerResponse.model_validate(payload)
