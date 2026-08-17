#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"
checkout_dir="${KMA_KYVERNO_REPO:-${project_dir}/../demo-pr-17067}"
transport="${KMA_TRANSPORT:-local-proxy}"

if [[ -z "${KMA_MODEL:-}" ]]; then
  printf 'error: KMA_MODEL must name a tool-capable model advertised by the selected transport\n' >&2
  exit 2
fi

for executable in uv git go bwrap; do
  if ! command -v "${executable}" >/dev/null 2>&1; then
    printf 'error: required executable is unavailable: %s\n' "${executable}" >&2
    exit 2
  fi
done

demo_runs="$(mktemp -d -t kma-rehearsal.XXXXXX)"
cd "${project_dir}"

uv sync --extra dev --extra model
uv run ruff check src tests
uv run pytest -q
uv run kma agent-doctor \
  --fixture fixtures/inputs/pr-17067-cel-go.json \
  --repo "${checkout_dir}" \
  --transport "${transport}"
uv run kma analyze-pr \
  --fixture fixtures/inputs/pr-17067-cel-go.json \
  --repo "${checkout_dir}" \
  --planner agent \
  --transport "${transport}" \
  --runs "${demo_runs}"
uv run kma replay-attack \
  --fixture fixtures/inputs/adversarial-workflow.json \
  --planner fixture \
  --runs "${demo_runs}"
uv run kma eval \
  --cases fixtures/inputs \
  --annotations fixtures/annotations \
  --planner fixture \
  --output "${demo_runs}/evaluation.json"

printf 'demo verification: passed\n'
printf 'artifacts: %s\n' "${demo_runs}"
