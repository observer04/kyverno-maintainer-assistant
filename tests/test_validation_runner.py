from __future__ import annotations

import pytest

from kma.validation_runner import OfflineBubblewrapRunner, ValidationRuntimeError


def test_validation_runner_rejects_any_non_go_test_command_before_runtime_probe(
    tmp_path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    runner = OfflineBubblewrapRunner(root, repository_revision="a" * 40)

    with pytest.raises(
        ValidationRuntimeError,
        match=r"^VALIDATION\.COMMAND_PROFILE_DENIED$",
    ):
        runner.run(
            target_id="unit.cel.compiler",
            command_argv=("sh", "-c", "cat /etc/passwd"),
            timeout_seconds=30,
            max_output_bytes=1024,
        )


def test_sandbox_argv_has_offline_read_only_boundary(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    goroot = tmp_path / "goroot"
    module_cache = tmp_path / "modules"
    goroot.mkdir()
    module_cache.mkdir()
    runner = OfflineBubblewrapRunner(root, repository_revision="a" * 40)

    argv = runner._sandbox_argv(
        goroot=goroot,
        module_cache=module_cache,
        command_argv=("go", "test", "./pkg/cel/compiler"),
        timeout_seconds=90,
    )

    assert "--unshare-all" in argv
    assert "--unshare-user" in argv
    assert "--disable-userns" in argv
    assert "--share-net" not in argv
    assert "--clearenv" in argv
    assert "--cap-drop" in argv
    assert argv[-3:] == ["/goroot/bin/go", "test", "./pkg/cel/compiler"]
    repository_mount = argv.index(str(root.resolve()))
    assert argv[repository_mount - 1] == "--ro-bind"
