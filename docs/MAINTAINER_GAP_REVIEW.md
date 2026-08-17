# Maintainer-Perspective Readiness and Gap Review

**Review basis:** the CNCF Kyverno AI Assistant listing and upstream Kyverno issue #16665

**Verdict:** strong application vertical slice; intentionally incomplete mentorship project

## What a Kyverno maintainer is likely evaluating

The question is not whether the demo contains a clever model. It is whether the applicant
understands the work maintainers actually need, the repository-specific constraints, and the path
from an impressive prototype to an operable service that reduces rather than creates toil.

This prototype provides credible evidence in three areas:

- **Phase 0 metadata:** a versioned, content-digested path-to-validation catalog grounded in
  Kyverno's API/codegen, CEL, engine, controller, CLI, conformance, workflow, dependency, and docs
  surfaces;
- **Phase 2 vertical slice:** an exact PR revision is classified, inspected through tools, mapped to
  validation, and one scoped CEL test is actually executed and cited;
- **Phase 1 safety groundwork:** isolated execution, strict tool contracts, credential separation,
  deny-by-default capabilities, full decision binding, idempotency, audit, and a kill switch.

## Honest coverage against the official phases

| Official phase or guardrail | Implemented evidence | Still missing |
|---|---|---|
| Phase 0: repo audit, agent docs, path-to-test map | Versioned catalog and Kyverno-specific rules | Maintainer-reviewed/upstreamed metadata, per-directory `AGENTS.md`, and any approved repo restructuring |
| Phase 1: sandbox + GitHub App + dependency/rebase workflows | Bubblewrap target runner, policy boundary, audit, idempotency, kill switch | GitHub App, verified webhooks, scheduler/queue, branch update, CI dispatch, comments/labels, and dependency auto-merge policy |
| Phase 2: diff-to-test mapper | Real PR #17067 flow and scoped CEL compiler execution | Maintainer-validated coverage map, broader Go/CLI/Chainsaw targets, precision/noise data from shadow operation |
| Phase 3: issue triage + repro | Architectural extension point only | Issue adapters, missing-info dialogue, KinD reproduction, artifact capture, and cleanup |
| Phase 4: grounded Q&A | Not implemented | Docs index/retrieval, Slack/Discussions integration, citations, freshness, and escalation |
| Auditable/reversible actions | Content-bound local audit and dry-run-only output | Production append-only telemetry and one updateable GitHub surface |
| Least privilege | No GitHub credential exists in the harness; validation has no network/credentials | Short-lived GitHub App token service and reviewed per-workflow permission matrix |
| Rate limit / kill switch | Model tool call/byte limits and tested policy kill switch | Queue-level rate limiting, repository config, operator control plane, and incident drill |

## What should stand out in selection

- The implementation is Kyverno-specific. It understands that API changes fan out into generated
  clients/CRDs/Helm/docs, generated files need provenance, CEL unit tests and Chainsaw suites cover
  different layers, and small dependency diffs can carry central runtime risk.
- The assistant is useful without pretending the model is authority. Rules-only operation remains
  conservative when the provider fails; model output can add caution but cannot remove safety.
- The model has real tools, including a real executor, but the tool shape enforces least authority:
  a target ID rather than model-authored shell.
- The demo measures baselines and shows a failure boundary. Ten applicant-annotated cases are
  architecture tests, explicitly not production accuracy claims.

## What must not be claimed in the video

- that the full AI Maintainer Assistant is complete;
- that Bubblewrap alone is a production sandbox for hostile multi-tenant execution;
- that a successful scoped test authorizes merge;
- that the path map is maintainer-approved or complete;
- that fixture evaluation establishes production accuracy;
- that GitHub scheduling, webhooks, rebase, issue reproduction, or docs Q&A exist.

## Proposed mentorship build order

1. Review the catalog and repository boundaries with maintainers; upstream the smallest useful
   Phase 0 metadata and define success/noise metrics.
2. Build GitHub App/webhook/queue scaffolding in shadow mode with short-lived credentials and a
   production job sandbox.
3. Validate the diff-to-test mapper on historical and live shadow traffic; expand to approved
   unit, codegen, CLI, and Chainsaw targets.
4. Add one reversible GitHub output, measure overrides and interruption cost, and only then consider
   dependency/rebase actions.
5. Extend the same evidence/policy/audit kernel to issue reproduction, followed by grounded Q&A as
   stretch work.

That sequence follows the proposal while leaving room for maintainer feedback to change mappings,
policies, and priority. The prototype demonstrates the engineering approach; the mentorship is
where it becomes an upstream-owned product.
