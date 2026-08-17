from __future__ import annotations

from argparse import Namespace

from kma import cli

from .conftest import INPUTS


class _UnavailablePlanner:
    planner_type = "agent"
    model_id = "unavailable-probe"

    def propose(self, snapshot):
        raise RuntimeError("provider detail must not leak")


def test_requested_live_planner_fallback_is_visible_and_nonzero(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(cli, "_planner", lambda *args, **kwargs: _UnavailablePlanner())
    args = Namespace(
        command="analyze-pr",
        fixture=INPUTS / "pr-17067-cel-go.json",
        runs=tmp_path / "runs",
        planner="agent",
        model="unavailable-probe",
        repo=tmp_path,
        transport="local-proxy",
        summary_only=True,
    )

    exit_code = cli._run(args)
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "planner: unavailable" in output
    assert "planner-error: PLANNER.UNAVAILABLE" in output
    assert "provider detail must not leak" not in output
    assert "<!-- kma:dry-run" not in output


def test_summary_only_is_available_for_recorded_commands() -> None:
    parser = cli.build_parser()

    analyze = parser.parse_args(
        ["analyze-pr", "--fixture", "fixture.json", "--summary-only"]
    )
    attack = parser.parse_args(
        ["replay-attack", "--fixture", "fixture.json", "--summary-only"]
    )

    assert analyze.summary_only is True
    assert attack.summary_only is True
