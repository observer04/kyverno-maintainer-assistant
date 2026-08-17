# First-Principles Video Direction and 4:30 Script

Use this as a presenter guide, not as text to memorize blindly. The **understand** notes are for
you; the blockquotes are the words to say. Replace only the bracketed personal details. Keep the
provider/proxy terminal and every credential off-screen.

## Understand the project before recording

### The problem in one sentence

Kyverno maintainers repeatedly have to inspect a change, work out its possible impact, choose the
right validation, and decide what is safe to do next. The proposal asks whether an AI assistant can
reduce that toil without gaining unsafe or noisy authority.

### The prototype in one sentence

The prototype is a guarded decision pipeline: it observes one exact pull-request revision, lets a
model investigate through narrow tools, runs one pre-approved test in an offline sandbox, combines
the model's judgment with Kyverno-specific rules, and produces an auditable dry run for a human.

### The five-question story

Remember this sequence; it is the logic of the whole video:

1. **Observe:** exactly which code revision are we discussing?
2. **Understand:** what could those changed files affect?
3. **Validate:** what useful test can safely run now?
4. **Authorize:** does that evidence justify an action, or is human review still required?
5. **Record:** can a maintainer reconstruct how the conclusion was reached?

The model helps with **understanding**. It does not own the other four responsibilities. The Python
harness owns the tools, test catalog, sandbox, rules, permissions, and audit record.

### Terms you must be comfortable explaining

- **Head SHA:** the unique commit fingerprint of the PR version being analyzed. Binding evidence to
  it prevents a result from an older version being reused after the code changes.
- **Path-to-test catalog:** a versioned lookup table connecting changed repository areas to relevant
  validation. The model chooses a target ID from this menu; it never writes a shell command.
- **Sandbox:** a locked execution room. Here the test gets read-only source and dependencies, a new
  temporary build cache, no credentials, and no network.
- **Monotonic reconciliation:** the model may add caution, but cannot remove a rule-required check,
  reduce risk, or cancel human escalation.
- **Dry run:** a proposed maintainer response with no GitHub mutation. The prototype does not merge,
  comment, label, rebase, or dispatch CI.
- **Trace digest:** a fingerprint over the recorded evidence trajectory. It makes later changes to
  the recorded content detectable; it is not a claim that a local file is a production append-only
  audit system.

## Recorded storyboard

### 0:00–0:20 — Introduce yourself (camera)

**Why this comes first:** give the reviewers a reason to connect your experience to the trust and
evaluation problem, not just to “AI.”

> Hi, I'm **[name]**, a final-year **[degree/discipline]** student focused on AI engineering,
> backend systems, and security. My recent work has made me especially interested in evaluating
> agentic systems and engineering the boundaries that make them dependable. That is what drew me
> to Kyverno's AI Assistant project.

**Transition:** “Before showing code, here is the maintainer problem I am trying to solve.”

### 0:20–0:50 — State the real problem (simple slide)

Show only:

```text
repeated maintainer work
        ↓
inspect → choose validation → decide → explain
```

**Why this matters:** reviewers should understand that the product is reduced maintainer toil—not a
chatbot and not autonomous merging.

> Maintainers repeatedly handle dependency updates, stale branches, test selection, issue
> reproduction, and recurring questions. Each task is manageable; the queue is the problem. The
> goal is to shorten that queue without replacing it with noisy bot comments or unsafe decisions.
> So I framed the assistant around five questions: what exact revision changed, what can it affect,
> what should run, what action is justified, and can the decision be audited?

**Transition:** “Those questions determine the architecture.”

### 0:50–1:30 — Explain the proposal (architecture screen)

Show `docs/ARCHITECTURE.md` and follow the diagram from left to right.

**What the viewer should learn:** repository text is untrusted, model judgment is fallible, and
GitHub authority is privileged, so they must not be collapsed into one prompt.

> Evidence is captured for one exact head commit. Kyverno-specific rules establish a safety floor,
> while a tool-using model investigates the pinned checkout and a versioned path-to-test catalog.
> The model can request a target ID, not arbitrary shell. The host resolves that ID and runs the
> fixed command offline. Finally, deterministic reconciliation prevents the model from lowering
> risk, and deny-by-default policy controls every outward capability.
>
> The model call itself is online through the official OpenAI Python SDK and Responses interface.
> The test sandbox is separately offline. Python owns the harness; Codex is the planner used through
> the API, not the application runtime or permission system.

**Transition:** “I implemented one complete path through that architecture rather than pretending
the entire mentorship project is already finished.”

### 1:30–1:47 — Scope it honestly (architecture screen)

> This prototype covers Phase 0 repository metadata and one Phase 2 diff-to-test path, with Phase 1
> safety groundwork. It does not yet contain a GitHub App, scheduler, rebase automation, issue
> reproduction, or documentation Q&A. The purpose is to prove the smallest useful and safe vertical
> slice, then validate it with maintainers.

**Transition:** “First I prove the conditions under which the result can be trusted.”

### 1:47–2:06 — Preflight the boundary (terminal)

Run the `agent-doctor` command from `docs/DEMO.md`.

**Why you run it:** a successful AI answer is meaningless if it used the wrong revision or had
hidden authority. Preflight proves those assumptions before displaying a result.

> The doctor confirms the exact real PR commit, the version and digest of the validation catalog,
> and the available model. More importantly, it proves path traversal and arbitrary shell are
> denied, and that the validator has read-only source with an unshared network. These are enforced
> properties, not instructions asking the model to behave.

**Transition:** “With those boundaries established, here is the normal useful case.”

### 2:06–3:04 — Analyze a real Kyverno PR (terminal)

Run the live `analyze-pr` command from `docs/DEMO.md`.

**What is happening:** PR #17067 changes only `go.mod` and `go.sum`, updating `cel-go` from 0.30 to
0.31. The point is that two changed files can still have a large behavioral impact because CEL is
central to Kyverno policy compilation and evaluation.

> The deterministic layer immediately requires dependency review, the full unit gate, and human
> review. The model then searches the real checkout, queries the validation catalog, and requests
> `unit.cel.compiler`. The host—not the model—turns that ID into
> `go test ./pkg/cel/compiler` and runs it without network or credentials.
>
> The trace records that the test passed, its exit code, the exact revision, and the observation the
> final proposal cites. That passing test is useful evidence, but it is not permission to merge. The
> broader dependency risk and missing release-note context keep the result at high-risk human
> escalation. Existing CI and branch protection remain authoritative.

**Transition:** “That shows usefulness when the planner behaves. Now assume it does not.”

### 3:04–3:33 — Fail safely under hostile input (terminal)

Run the `replay-attack` command from `docs/DEMO.md`.

**Why use a replay:** a deterministic hostile proposal lets the audience see the real policy
boundary fail safely every time. Do not describe it as a live contributor incident.

> This synthetic workflow patch contains instructions to reveal a secret and merge. The replay
> deliberately sends both proposals to the real policy boundary. I am not claiming prompt
> injection is solved. I am showing that the model cannot grant itself authority: neither action is
> an executable tool, policy denies both, and the only output is still a dry run.

**Transition:** “One example can be staged, so I also compare the design against simpler baselines.”

### 3:33–3:55 — Evaluate the architecture (terminal)

Run the `eval` command only if you remain within five minutes.

> These are ten applicant-annotated architecture cases, not a production benchmark. Rules-only is
> conservative but misses semantic nuance. Model-only misses required checks and proposes unsafe
> actions. The hybrid preserves the deterministic safety floor while using the model for repository
> investigation. The next valid step is maintainer-reviewed labels and a larger shadow dataset.

**Transition:** “That leads directly to what I would build during the mentorship.”

### 3:55–4:30 — Roadmap and close (roadmap slide, then camera)

> If selected, I would first review and upstream the repository metadata with maintainers and agree
> on precision, noise, and override metrics. Next I would add GitHub App, webhook, queue, and
> production sandbox scaffolding in shadow mode; expand approved Go, CLI, codegen, and Chainsaw
> targets; and only then enable one reversible GitHub action. Issue reproduction follows, with
> grounded Q&A as stretch work.
>
> My proposal is not to let an LLM maintain Kyverno. It is to turn routine maintenance into a
> measurable, evidence-driven workflow where autonomy is earned one permission at a time. Thank
> you for considering my application.

## Delivery rules

- Speak to the reviewer, not to the terminal. Start each command, then explain the result while it
  runs or immediately afterward.
- Point to three proof lines only: the sandbox boundary, the passed validation observation, and the
  denied hostile capabilities. Do not read the full output.
- Say **prototype** or **vertical slice**, never “completed assistant” or “production-ready.”
- Say **the model requested a catalog target**, never “the model ran a shell command.”
- Say **passing evidence**, never “safe to merge.”
- Say **applicant-annotated cases**, never “accuracy benchmark.”
- If the live planner fails or falls back, stop recording. Never present a fixture replay as a live
  model run.

## Likely maintainer questions

**Why use a model at all?** Repository search, semantic blast-radius reasoning, and explaining
uncertainty do not fit a static path map well. Rules remain better for invariant safety checks.

**Why not let it run any test command?** Model-authored argv turns reasoning errors or prompt
injection into code execution. A reviewed target catalog gives useful choice without arbitrary
authority.

**Why does the scoped test pass but the result escalate?** It proves one local compatibility
property. It does not establish dependency provenance, full regression safety, or release behavior.

**What is genuinely missing?** Maintainer-approved metadata, GitHub App/webhook/queue operation, a
production job sandbox, historical shadow evaluation, rebase/dependency workflows, issue
reproduction, and grounded Q&A.

**What changes if maintainers dislike the mapping?** The catalog is versioned policy data, not
hidden prompt logic. It can be reviewed, tested, changed, or removed without replacing the agent.
