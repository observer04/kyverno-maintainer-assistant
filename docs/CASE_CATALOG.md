# Evaluation Case Catalogue

The case set is intentionally small and evidence-rich. All annotations are labeled `applicant_annotation`; none claim maintainer consensus.

| Case | Fixture | Origin | Lesson |
|---|---|---|---|
| C01 | `pr-17066-actions-dependency` | Public PR lesson | A workflow dependency needs workflow review, not unrelated Kyverno runtime tests |
| C02 | `pr-17067-cel-go` | Bounded GitHub capture | A small central CEL dependency update can have broad semantic impact |
| C03 | `pr-16721-cel-codegen` | Public PR lesson | CEL source, generated CRDs, docs, and a named conformance suite interact |
| C04 | `pr-16838-background-controller` | Public PR lesson | Background/controllers map to package and asynchronous behavior tests |
| C05 | `pr-16945-security-dependency` | Public PR lesson | A security-motivated patch dependency update remains human-reviewed |
| C06 | `pr-16891-cross-package-cel` | Public PR lesson | Cross-package behavior defeats nearest-directory test selection |
| C07 | `docs-only` | Synthetic control | Documentation-only work should respect CI and notification budgets |
| C08 | `api-codegen` | Synthetic control | API changes produce generated fan-out and compatibility review |
| C09 | `adversarial-workflow` | Synthetic mutation | Injected secret/merge instructions cannot obtain capabilities |
| C10 | `stale-checks` | Synthetic mutation | Successful checks from another head SHA cannot reassure the current revision |

Only C02 preserves the real PR subject, base/head revisions, changed-file patches, labels, and a
bounded set of head-bound checks. C01 and C03–C06 are purpose-built lessons associated with public
PRs, not exact historical reproductions. Synthetic controls have `source_url: null`. None of these
applicant annotations claim maintainer consensus.

Annotations record:

- must-run checks;
- acceptable alternatives;
- explicitly unnecessary checks;
- minimum risk;
- forbidden capabilities;
- required escalation;
- expected rule IDs;
- uncertainty and rationale.

Annotations never enter the planner input directory.
