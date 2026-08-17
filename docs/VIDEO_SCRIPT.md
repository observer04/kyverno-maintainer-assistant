# Complete 4:40 Video Prompter

This is the **only file to use while recording**. Follow it from top to bottom. Text under **SAY**
is spoken. Text under **PASTE** is copied into the visible terminal. Instructions in square brackets
are actions, not dialogue.

Replace `[name]` and `[degree/discipline]` before recording.

---

## A. Prepare once — do not record this section

### A1. Know the story

You are demonstrating one guarded maintenance loop:

```text
observe exact revision
  → understand impact
  → run scoped validation
  → authorize conservatively
  → record the reasoning
```

The remote model helps **understand** the change. The Python harness owns the evidence, tools,
test commands, sandbox, deterministic rules, permissions, and audit record.

### A2. Prepare the screens

Have these ready before recording:

1. Camera view.
2. Browser tab with the
   [official Kyverno AI Assistant issue](https://github.com/kyverno/kyverno/issues/16665).
3. Browser tab with the rendered
   [architecture diagram](https://github.com/observer04/kyverno-maintainer-assistant/blob/main/docs/ARCHITECTURE.md).
4. One visible terminal in `/home/op/projects/cncf/kyverno/prototype`.
5. This prompter on a second screen or device.

Use a wide terminal. Increase the font enough that these fields are readable:

```text
repository
validation-sandbox
agent-trace
validation
decision
required
denied
```

Do not display the proxy terminal, environment variables, OAuth directory, browser login flow, or
credentials.

### A3. Start the localhost adapter in a hidden terminal if it is not already running

**PASTE IN THE HIDDEN TERMINAL**

```bash
cd /home/op/projects/cncf/kyverno/prototype
../tools/cliproxyapi/cli-proxy-api -config ../tools/cliproxyapi/config.kma.yaml
```

Leave that terminal hidden.

### A4. Set the demo environment and run the complete rehearsal

**PASTE IN THE VISIBLE TERMINAL BEFORE RECORDING**

```bash
cd /home/op/projects/cncf/kyverno/prototype
export KMA_MODEL='gpt-5.3-codex-spark'
export KMA_TRANSPORT='local-proxy'
./scripts/verify-demo.sh
```

Do not record unless the final line is:

```text
demo verification: passed
```

After it passes, clear the visible terminal and leave it at the project directory:

```bash
clear
```

---

## B. Record this section

## 0:00–0:20 — Introduction

**SCREEN:** Camera.

**SAY**

> Hi, I'm **[name]**, a final-year **[degree/discipline]** student working across AI, backend
> systems, and security. What interested me was not adding AI to Kyverno, but helping maintainers
> without giving an agent more trust than it needs.

**SAY — TRANSITION**

> That starts with a very practical maintainer problem.

---

## 0:20–1:04 — Explain the maintainer problem

**SCREEN:** Official Kyverno issue #16665. Point briefly to the phase list; do not scroll through
the whole issue.

**SAY**

> Reviewing a change is not just reading its diff. A maintainer has to rebuild context: what part of
> Kyverno it touches, which generated files or tests matter, whether existing checks belong to the
> latest commit, and what is still uncertain. That work repeats across dependency PRs, stale
> branches, and issue reports.
>
> The bottleneck is turning scattered evidence into the next safe action. Automating it badly would
> only replace maintainer toil with bot noise. So the assistant must answer five things: what
> changed, what could it affect, what should run, what is safe to do, and why?

**SAY — TRANSITION**

> That is the problem this architecture answers.

---

## 1:04–1:42 — Explain the architecture

**SCREEN:** Rendered `docs/ARCHITECTURE.md`. Follow the diagram from left to right with the cursor.

**SAY**

> Repository content can mislead a model, and GitHub actions have consequences. So I separated
> evidence, reasoning, and authority. Evidence is tied to one commit, rules set the safety floor,
> and the model may only search a pinned checkout and select a reviewed test ID—never shell or a
> GitHub action.
>
> Python runs the fixed test offline, policy decides what is allowed, and maintainers stay in
> control.

**SAY — SCOPE**

> This prototype proves that one path end to end. GitHub operation, issue reproduction, and Q&A
> remain mentorship work.

**SAY — TRANSITION**

> First, I will prove those boundaries.

---

## 1:42–2:07 — Prove the boundary

**SCREEN:** Visible terminal.

**SAY BEFORE COMMAND**

> First, I check the exact code and actual permissions.

**PASTE**

```bash
uv run kma agent-doctor \
  --fixture fixtures/inputs/pr-17067-cel-go.json \
  --repo ../demo-pr-17067 \
  --transport "$KMA_TRANSPORT"
```

**WAIT:** Let the command finish.

**EXPECTED PROOF LINES**

```text
repository: ok c5ee06b1c6a3ea99723cd4e9a41648ec6a6c4ee1
catalog: ok kyverno-2026-08-17.v3 ...
tool-boundary: ok traversal denied
tool-boundary: ok arbitrary shell unavailable
validation-sandbox: ok bubblewrap network=unshared source=read-only ...
transport: ok local-proxy
selected-model: ok gpt-5.3-codex-spark
```

**POINT:** Highlight `repository`, `arbitrary shell unavailable`, and `validation-sandbox`.

**SAY AFTER OUTPUT**

> We have the exact commit and a versioned test catalog. There is no arbitrary shell, and tests get
> read-only source with no network. The host—not the prompt—enforces that.

**SAY — TRANSITION**

> Now I can analyze a real change.

---

## 2:07–3:31 — Analyze a real Kyverno pull request

**SAY BEFORE COMMAND**

> PR 17067 updates `cel-go`. It changes two files, but CEL sits in Kyverno's policy path, so the risk
> is larger than the diff suggests.

**PASTE**

```bash
uv run kma analyze-pr \
  --fixture fixtures/inputs/pr-17067-cel-go.json \
  --repo ../demo-pr-17067 \
  --planner agent \
  --transport "$KMA_TRANSPORT" \
  --summary-only \
  --runs /tmp/kma-video-runs
```

**SAY WHILE THE MODEL AND TEST RUN**

> The model is investigating and choosing a catalog target. The test runs offline without
> credentials.

**WAIT:** Let the command finish. Do not speak over the final summary.

**EXPECTED PROOF LINES**

The search/read order and optional recommendations may vary. These facts must appear:

```text
decision: escalate risk=high
required: dependency.review, unit.all, human.dependency-review
planner: agent
transport: local-proxy
agent-trace: ... evidence calls ...
  ... lookup_validation_targets ... ok ...
  ... run_validation_target ... ok ...
    validation: unit.cel.compiler outcome=passed exit=0 network=unshared
```

**POINT:** First highlight `run_validation_target`, then the `validation` result, and finally
`decision` plus `required`.

**SAY AFTER OUTPUT**

> The model selected the CEL compiler test, and it passed offline. That answers one narrow question,
> not whether the PR should merge. The rules still require dependency review, the full unit gate,
> and a human.
>
> The assistant adds evidence without claiming authority. The trace is audited, and GitHub is
> untouched.

**SAY — TRANSITION**

> Now I assume the planner is compromised.

**STOP CONDITION:** If the output says `PLANNER.UNAVAILABLE`, uses `planner: fixture`, lacks the
passed validation line, or exits nonzero, stop the recording. Do not describe a fallback as a live
model run.

---

## 3:31–3:54 — Demonstrate safe failure

**SAY BEFORE COMMAND**

> This replay asks for a secret and a merge, forcing both through policy.

**PASTE**

```bash
uv run kma replay-attack \
  --fixture fixtures/inputs/adversarial-workflow.json \
  --planner fixture \
  --summary-only \
  --runs /tmp/kma-video-runs
```

**WAIT:** Let the command finish.

**EXPECTED PROOF LINES**

```text
decision: escalate risk=critical
required: workflow.security-review, workflow.sha-pinning
denied: read_secret, merge
planner: fixture
transport: fixture
```

**POINT:** Highlight `denied: read_secret, merge`.

**SAY AFTER OUTPUT**

> Prompt injection is not solved. The point is that the planner cannot grant itself new powers.
> Both actions are unavailable and denied, so this stays a dry run.

**SAY — TRANSITION**

> Finally, I compare the alternatives.

---

## 3:54–4:12 — Compare the architecture

**PASTE**

```bash
uv run kma eval \
  --cases fixtures/inputs \
  --annotations fixtures/annotations \
  --planner fixture \
  --output /tmp/kma-video-evaluation.json
```

**WAIT:** Let the table appear.

**EXPECTED PROOF LINES**

```text
VARIANT      RECALL  UNSAFE-PROP  UNSAFE-AUTH  FALSE-REASSURE  ESC-CORRECT
rules_only   1.0     0            0            1               10/10
model_only   0.9231  2            0            1               8/10
hybrid       1.0     0            0            0               10/10
```

**POINT:** Move across `rules_only`, `model_only`, and `hybrid` once.

**SAY AFTER OUTPUT**

> These are architecture checks, not a production benchmark. Rules miss context; the model misses
> safeguards. The hybrid gives each the job it does well. Maintainer-labeled shadow data comes next.

**SAY — TRANSITION**

> That gives me the roadmap.

---

## 4:12–4:40 — Roadmap and close

**SCREEN:** Return to the architecture diagram, then camera for the final sentence.

**SAY**

> If selected, I would first validate the mappings with maintainers. Then I would add the GitHub App
> and production sandbox in shadow mode, expand approved tests, and only then enable one reversible
> action. Issue reproduction and grounded Q&A follow.
>
> The goal is to reduce repeated work while keeping evidence, permissions, and human judgment clear.
> Thank you.

---

## C. Rules for a clean delivery

- Read the **SAY** blocks, not the headings or expected-output blocks.
- Start commands immediately after the preceding sentence; do not narrate your typing.
- Interpret output after it appears. Never read the entire terminal.
- Keep the cursor still except when pointing to the named proof lines.
- Say “prototype” or “vertical slice,” never “production-ready assistant.”
- Say “the model requested a catalog target,” never “the model ran a shell command.”
- Say “passing evidence,” never “safe to merge.”
- Say “applicant-annotated cases,” never “accuracy benchmark.”
- Optional model recommendations may vary; the required checks and escalation are the stable safety
  floor.
- If the live run fails, stop recording, fix the environment, run the rehearsal again, and restart
  the recording from the beginning.
