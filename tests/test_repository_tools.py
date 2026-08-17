from __future__ import annotations

import json
import subprocess

import pytest

from kma.repository_tools import RepositoryToolHost


class PassingValidationRunner:
    def __init__(self) -> None:
        self.calls = []

    def readiness(self):
        return {
            "backend": "test-sandbox",
            "network": "unshared",
            "source_mount": "read-only",
            "environment": "cleared",
            "go_version": "go1.26.5",
        }

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "target_id": kwargs["target_id"],
            "outcome": "passed",
            "exit_code": 0,
            "repository_revision": "test-revision",
            "command_argv": list(kwargs["command_argv"]),
            "command_digest": "sha256:" + "1" * 64,
            "sandbox": {"network": "unshared"},
            "stdout_preview": "ok",
            "stderr_preview": "",
            "stdout_digest": "sha256:" + "2" * 64,
            "stderr_digest": "sha256:" + "3" * 64,
            "output_truncated": False,
            "duration_ms": 1,
        }


def make_repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "go.mod").write_text(
        "module example.test/repo\nrequire github.com/google/cel-go v0.31.0\n",
        encoding="utf-8",
    )
    package = root / "pkg" / "cel" / "compiler"
    package.mkdir(parents=True)
    (package / "compiler.go").write_text(
        'package compiler\nimport "github.com/google/cel-go/cel"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "KMA Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "kma@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, revision


def test_repository_tools_produce_revision_bound_evidence(tmp_path) -> None:
    root, revision = make_repository(tmp_path)
    host = RepositoryToolHost(root, expected_revision=revision)

    lookup = host.execute(
        "lookup_validation_targets",
        json.dumps({"changed_paths": ["go.mod"]}),
        "call-lookup",
    )
    search = host.execute(
        "search_repository",
        json.dumps(
            {
                "query": "github.com/google/cel-go",
                "paths": ["pkg/cel"],
                "max_results": 5,
            }
        ),
        "call-search",
    )
    read = host.execute(
        "read_repository_file",
        json.dumps({"path": "go.mod", "start_line": 1, "end_line": 2}),
        "call-read",
    )
    codegen = host.execute(
        "lookup_validation_targets",
        json.dumps({"changed_paths": ["api/kyverno/v1/policy_types.go"]}),
        "call-codegen",
    )

    assert lookup["status"] == search["status"] == read["status"] == codegen["status"] == "ok"
    assert {item["target_id"] for item in lookup["data"]["targets"]} == {
        "dependency.review",
        "unit.all",
        "unit.cel.compiler",
    }
    codegen_target = next(
        item for item in codegen["data"]["targets"] if item["target_id"] == "codegen.verify"
    )
    assert codegen_target["command_sequence_argv"] == [
        ["make", "codegen-all-code"],
        ["make", "verify-codegen"],
    ]
    assert search["data"]["matches"][0]["path"] == "pkg/cel/compiler/compiler.go"
    trace = host.trace()
    assert trace.repository_revision == revision
    assert [item.observation_id for item in trace.observations] == [
        "tool.0001",
        "tool.0002",
        "tool.0003",
        "tool.0004",
    ]
    assert all(item.repository_revision == revision for item in trace.observations)


@pytest.mark.parametrize(
    ("tool_name", "arguments", "reason"),
    [
        (
            "read_repository_file",
            {"path": "../outside", "start_line": 1, "end_line": 2},
            "TOOL.PATH_OUTSIDE_REPOSITORY",
        ),
        (
            "read_repository_file",
            {"path": ".git/config", "start_line": 1, "end_line": 2},
            "TOOL.SENSITIVE_PATH_DENIED",
        ),
        ("run_shell", {"command": "cat /etc/passwd"}, "TOOL.UNKNOWN_TOOL"),
    ],
)
def test_repository_tools_deny_boundary_crossing(
    tmp_path, tool_name: str, arguments: dict[str, object], reason: str
) -> None:
    root, revision = make_repository(tmp_path)
    host = RepositoryToolHost(root, expected_revision=revision)

    output = host.execute(tool_name, json.dumps(arguments), "call-denied")

    assert output == {
        "observation_id": "tool.0001",
        "status": "denied",
        "data": {"error": reason},
    }
    assert host.trace().observations[0].reason_code == reason


def test_repository_preconditions_reject_wrong_revision_and_dirty_tree(tmp_path) -> None:
    root, revision = make_repository(tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        RepositoryToolHost(root, expected_revision="0" * 40)

    (root / "untracked.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(ValueError, match="must be clean"):
        RepositoryToolHost(root, expected_revision=revision)


def test_repository_tools_deny_intermediate_symlink(tmp_path) -> None:
    root, _ = make_repository(tmp_path)
    (root / "metadata").symlink_to(root / ".git", target_is_directory=True)
    subprocess.run(["git", "-C", str(root), "add", "metadata"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "add symlink"], check=True)
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    host = RepositoryToolHost(root, expected_revision=revision)

    output = host.execute(
        "read_repository_file",
        json.dumps({"path": "metadata/config", "start_line": 1, "end_line": 2}),
        "call-symlink",
    )

    assert output["status"] == "denied"
    assert output["data"]["error"] == "TOOL.SYMLINK_DENIED"


def test_validation_tool_resolves_catalog_argv_without_model_command(tmp_path) -> None:
    root, revision = make_repository(tmp_path)
    runner = PassingValidationRunner()
    host = RepositoryToolHost(
        root,
        expected_revision=revision,
        validation_runner=runner,
    )

    output = host.execute(
        "run_validation_target",
        json.dumps({"target_id": "unit.cel.compiler"}),
        "call-run",
    )

    assert output["status"] == "ok"
    assert output["data"]["outcome"] == "passed"
    assert runner.calls == [
        {
            "target_id": "unit.cel.compiler",
            "command_argv": ("go", "test", "./pkg/cel/compiler"),
            "timeout_seconds": 90,
            "max_output_bytes": 16000,
        }
    ]
    observation = host.trace().observations[0]
    assert observation.evidence_paths == ("pkg/cel/compiler",)
    assert observation.validation_target == "unit.cel.compiler"
    assert observation.validation_outcome == "passed"
    assert observation.validation_exit_code == 0
    assert observation.validation_network == "unshared"
    assert "catalog_digest" in output["data"]


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"target_id": "unit.all"}, "VALIDATION.TARGET_NOT_EXECUTABLE"),
        ({"target_id": "not.real"}, "VALIDATION.UNKNOWN_TARGET"),
        (
            {"target_id": "unit.cel.compiler", "command": "cat /etc/passwd"},
            "TOOL.INVALID_ARGUMENTS",
        ),
    ],
)
def test_validation_tool_denies_non_catalog_or_model_authored_commands(
    tmp_path, arguments: dict[str, str], reason: str
) -> None:
    root, revision = make_repository(tmp_path)
    host = RepositoryToolHost(
        root,
        expected_revision=revision,
        validation_runner=PassingValidationRunner(),
    )

    output = host.execute("run_validation_target", json.dumps(arguments), "call-denied")

    assert output["status"] == "denied" if reason.startswith("VALIDATION") else "error"
    assert output["data"]["error"] == reason
