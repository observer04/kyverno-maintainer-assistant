from __future__ import annotations

from pathlib import Path

import pytest

from kma.evidence import build_snapshot, load_fixture
from kma.planner import FixturePlanner, run_planner
from kma.reconcile import reconcile
from kma.rules import evaluate_rules, load_registry

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "fixtures" / "inputs"
ANNOTATIONS = ROOT / "fixtures" / "annotations"


@pytest.fixture
def fixture_planner() -> FixturePlanner:
    return FixturePlanner()


def analyzed(fixture_id: str):
    fixture = load_fixture(INPUTS / f"{fixture_id}.json")
    snapshot = build_snapshot(fixture)
    rules = evaluate_rules(snapshot, load_registry())
    planner = run_planner(FixturePlanner(), snapshot)
    analysis = reconcile(snapshot, rules, planner)
    return snapshot, rules, planner, analysis
