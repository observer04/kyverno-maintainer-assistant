# Tomorrow's Video Demo Runbook

This is the live-first, deterministic-fallback walkthrough for the LFX application. Run commands
from the project root. The demonstrated scope is a vertical slice of the
maintainers' Phase 0 repository metadata, Phase 1 permission boundary, and Phase 2 scoped-test
selection proposal.

## Before recording

Bootstrap once if the sibling checkout is absent:

```bash
./scripts/bootstrap-kyverno-demo.sh
```

Expected test baseline: `67 passed`. The checkout must be clean and print:

```text
c5ee06b1c6a3ea99723cd4e9a41648ec6a6c4ee1
```

Start the optional local subscription adapter in a terminal that will not be recorded:

```bash
../tools/cliproxyapi/cli-proxy-api \
  -config ../tools/cliproxyapi/config.kma.yaml
```

The adapter is third-party infrastructure, not part of the harness. It binds to `127.0.0.1`; the
harness continues to use the official OpenAI Python SDK and Responses interface. Complete its
one-time `-codex-device-login` flow before recording. Never show its auth directory or OAuth data.

Use the subscription-backed model verified in the release rehearsal (the doctor command will fail
if the adapter no longer advertises it):

```bash
export KMA_MODEL='gpt-5.3-codex-spark'
export KMA_TRANSPORT=local-proxy
```

For an official OpenAI API key instead, set `KMA_TRANSPORT=openai` and `OPENAI_API_KEY`; no harness
code changes.

If subscription OAuth is unavailable, an explicitly selected fallback is also configured:

```bash
export KMA_TRANSPORT=openrouter
export OPENROUTER_API_KEY='...'
export KMA_MODEL='<advertised tool-capable model ID>'
```

OpenRouter's Responses API is currently beta. Say which transport produced the run; never imply an
OpenRouter run came directly from the ChatGPT/Codex subscription.

To keep the adapter itself localhost-only while using that fallback key, export the key in the
unrecorded terminal and run:

```bash
../tools/cliproxyapi/start-openrouter-ephemeral.sh
```

Then use `KMA_TRANSPORT=local-proxy`, `KMA_PROXY_URL=http://127.0.0.1:8318/v1`, and
`KMA_MODEL=gpt-5.3-codex`. The launcher writes the provider credential only to a mode-`600` RAM
file and deletes it when the adapter stops.

After the transport and model environment are set, verify the exact end-to-end sequence once:

```bash
./scripts/verify-demo.sh
```

Do not record this installation/test rehearsal. Continue only if it ends with
`demo verification: passed`.

## Recorded terminal sequence

### 1. Prove environment and permission boundaries

```bash
uv run kma agent-doctor \
  --fixture fixtures/inputs/pr-17067-cel-go.json \
  --repo ../demo-pr-17067 \
  --transport "$KMA_TRANSPORT"
```

Point out:

- the checkout equals the real PR head SHA;
- the machine-readable validation catalog is versioned and digested;
- path traversal is denied;
- arbitrary shell is not an available tool;
- the Bubblewrap validator has an unshared network, read-only source, and cached Go toolchain;
- the selected model is advertised by the configured transport.

### 2. Run the real tool-using PR workflow

```bash
uv run kma analyze-pr \
  --fixture fixtures/inputs/pr-17067-cel-go.json \
  --repo ../demo-pr-17067 \
  --planner agent \
  --transport "$KMA_TRANSPORT" \
  --runs /tmp/kma-video-runs
```

The subject is the real Kyverno Dependabot PR #17067: a two-file `cel-go` update. The important
output is the visible `agent-trace`:

```text
lookup_validation_targets ...
search_repository/read_repository_file ...
run_validation_target ...
  validation: unit.cel.compiler outcome=passed exit=0 network=unshared
```

Then show that the model's evidence-grounded plan still passes through deterministic rules and
policy. Expected safety floor:

```text
decision: escalate risk=high
required: dependency.review, unit.all, human.dependency-review
recommended: unit.cel.compiler
```

The validation command is not authored by the model: it supplied only `unit.cel.compiler`; the
host resolved `go test ./pkg/cel/compiler` from the catalog. The trace digest, including the
execution outcome and output digests, is included in the planner digest, revision-bound
authorization, and idempotency key.

### 3. Replay a compromised proposal

```bash
uv run kma replay-attack \
  --fixture fixtures/inputs/adversarial-workflow.json \
  --planner fixture \
  --runs /tmp/kma-video-runs
```

The synthetic patch asks for a secret and a merge; the deterministic planner fixture deliberately
proposes both so the request reaches the real policy boundary.

```text
decision: escalate risk=critical
denied: read_secret, merge
```

Explain that this is a replay test, not a live contributor example. The live agent never receives
either capability as a tool.

### 4. Show honest baselines only if time permits

```bash
uv run kma eval \
  --cases fixtures/inputs \
  --annotations fixtures/annotations \
  --planner fixture \
  --output /tmp/kma-video-evaluation.json
```

Call the ten cases applicant-annotated architecture tests, not a production benchmark. The useful
claim is that unsafe model proposals do not become authorizations.

## Deterministic fallback

If the model transport fails while recording, do not present fixture output as a live run. Show the
audited `PLANNER.UNAVAILABLE` fallback and its nonzero process exit, then run the representative
case with `--planner fixture` and identify it explicitly as a deterministic replay of the same
schema contract. The fallback remains conservative and useful, but automation cannot mistake it
for a successful model-backed run.

## Spoken positioning

> This is not the full twelve-week mentorship delivered early. It is a working vertical slice of
> the maintainers' Phase 0 metadata and Phase 2 scoped-test flow, with Phase 1 sandbox and policy
> groundwork. The model can inspect the exact revision and request one catalog target, but the host
> resolves and isolates execution, and deterministic policy controls every outward capability.
