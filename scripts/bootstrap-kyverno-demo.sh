#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"
checkout_dir="${1:-${project_dir}/../demo-pr-17067}"
expected_revision="c5ee06b1c6a3ea99723cd4e9a41648ec6a6c4ee1"

if [[ -e "${checkout_dir}" ]]; then
  if ! git -C "${checkout_dir}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'error: destination exists but is not a Git checkout: %s\n' "${checkout_dir}" >&2
    exit 2
  fi
else
  git init --quiet "${checkout_dir}"
  git -C "${checkout_dir}" remote add origin https://github.com/kyverno/kyverno.git
  git -C "${checkout_dir}" fetch --quiet --depth 1 origin refs/pull/17067/head
  git -C "${checkout_dir}" checkout --quiet --detach FETCH_HEAD
fi

actual_revision="$(git -C "${checkout_dir}" rev-parse HEAD)"
if [[ "${actual_revision}" != "${expected_revision}" ]]; then
  printf 'error: checkout is %s; expected %s\n' "${actual_revision}" "${expected_revision}" >&2
  exit 2
fi
if [[ -n "$(git -C "${checkout_dir}" status --porcelain)" ]]; then
  printf 'error: checkout must be clean: %s\n' "${checkout_dir}" >&2
  exit 2
fi

GOTOOLCHAIN=auto go -C "${checkout_dir}" env GOROOT >/dev/null
GOTOOLCHAIN=auto go -C "${checkout_dir}" mod download

printf 'checkout: ok %s\n' "${actual_revision}"
printf 'dependencies: cached for offline validation\n'
printf 'path: %s\n' "${checkout_dir}"
