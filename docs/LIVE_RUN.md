# Live Responses Tool-Loop Verification

**Date:** 2026-08-17

**Status:** Current subscription-backed release rehearsal passed; not an evaluation result

## Current release rehearsal

The final application path was verified on 2026-08-17:

```text
official OpenAI Python SDK
  -> stateless Responses function calls
  -> CLIProxyAPI on 127.0.0.1:8317
  -> existing ChatGPT/Codex subscription OAuth
  -> gpt-5.3-codex-spark
```

- Run ID: `run_cb669bfdc7a011bb`
- Subject: real Kyverno PR #17067 at `c5ee06b1c6a3ea99723cd4e9a41648ec6a6c4ee1`
- Planner/transport: `agent` / `local-proxy`
- Trace digest: `sha256:fbf860f943f85867350f9b330078b737e1c2ad5fcc52032f331a0a20fd4aee74`
- Evidence trajectory: repository tree, repository search, catalog lookup, offline validation
- Validation: `unit.cel.compiler` passed, exit `0`, network `unshared`
- Final decision: `escalate`, risk `high`
- Required: `dependency.review`, `unit.all`, `human.dependency-review`
- Model addition: `unit.cel.compiler`

The harness closed evidence tools after the required lookup, repository inspection, and validation,
so the next model round could only call the strict submission function. There were four successful
evidence observations, no denied calls, and no GitHub mutation. The complete release rehearsal also
ran formatting checks, all 67 tests, the doctor, the live flow, the hostile replay, and the ten-case
evaluation; it ended with `demo verification: passed`.

## Current offline execution verification

After the original live-model rehearsal, the tool host gained a catalog-bound executor. On
2026-08-17, `unit.cel.compiler` ran successfully at the exact PR head
`c5ee06b1c6a3ea99723cd4e9a41648ec6a6c4ee1`:

```text
fixed argv: go test ./pkg/cel/compiler
outcome: passed
exit: 0
duration: 34.982s (cold build cache)
network namespace: unshared
source/module cache: read-only
stdout: ok github.com/kyverno/kyverno/pkg/cel/compiler
```

The execution tool and current prompt are covered by the 67-test suite and the complete updated
Responses trajectory (model inspection → target execution → submitted plan) above. The cold-build
timing is retained as a conservative isolation check; the release rehearsal uses the warmed module
cache and completed the live workflow successfully.

## Historical transport disclosure

The successful rehearsal used this route:

```text
official OpenAI Python SDK
  -> stateless Responses function calls
  -> CLIProxyAPI on 127.0.0.1:8318
  -> OpenRouter API-key route
  -> openai/gpt-5.3-codex
```

This was not a direct ChatGPT-subscription run. No provider key was written to the repository or
printed; the adapter used a permission-locked RAM file that was deleted on shutdown. A later audit
schema revision records the selected non-secret transport in `PlannerRecord`.

## Historical verified run

- Run ID: `run_a4f81c406c41234c`
- Subject: real Kyverno PR #17067 at `c5ee06b1c6a3ea99723cd4e9a41648ec6a6c4ee1`
- Planner: `agent`
- Model alias: `gpt-5.3-codex`
- Trace digest: `sha256:2051fcc12eb4417a2ac66ce3275a2c53272d355b4c44661209981f75d83fb4d2`
- Final status: `escalate`, risk `high`
- Required: `dependency.review`, `unit.all`, `human.dependency-review`
- Model additions: `unit.cel`, `conformance.cel`
- Policy-denied proposals: `dispatch_workflow`, `post_comment`

The model successfully queried `lookup_validation_targets`, searched real repository usage of
`github.com/google/cel-go`, listed workflows, read the unit-test workflow, cited tool observation
IDs, and submitted a strict proposal. Deterministic rules preserved the risk floor and required
checks; policy denied capabilities outside the dry-run allowlist.

## Honest failure observed

The trajectory used seven recorded attempts: four succeeded, two had invalid arguments, and the
seventh was denied after the six-call evidence budget. This exposed two demo-quality issues without
breaking the safety boundary:

1. the prompt did not tell the model the concrete call budget or encourage early submission;
2. the ordinary analysis prompt did not limit proposals to dry-run render capabilities.

Both were corrected after the run. A second provider attempt then returned HTTP `402`, so it was
not retried or presented as a successful verification. The host emitted an audited
`PLANNER.UNAVAILABLE` fallback, retained deterministic checks, and returned a nonzero process exit.

Before recording, rerun the updated prompt with either approved subscription OAuth or funded
OpenRouter access. Do not substitute the deterministic fixture planner and call it live.
