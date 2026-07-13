# Author-attested human review and adjudication v7

## Provenance scope

On 2026-07-13, the author explicitly confirmed that the decisions in the two frozen source workbooks were made by two human reviewers. The workbooks were generated from AI-assisted templates and retain legacy `SIM-A`/`SIM-B`, AIGC, and simulation wording. The source files therefore document the recorded decisions, while their human provenance is author-attested rather than independently established by document metadata. The source hashes are frozen in the reviewer CSVs and the provenance note.

## Completeness

- Reviewer A: 240/240 decisions; {'接受审校结论': 240}.
- Reviewer B: 240/240 decisions; {'接受审校结论': 192, '保留原标签': 40, '不确定': 8}.
- Shared task universe: 240/240 rows.
- Structured-field edits: none; normalized object, field, expected-state, and forbidden-effect agreement are all 1.000.

## Agreement

- Four-category decision agreement: 0.800 (192/240).
- Four-category decision Cohen's kappa: 0.000. Reviewer A used only `接受审校结论`, so this value is dominated by marginal imbalance and is not used as the primary reliability estimate.
- Joint binary-label coverage: 232/240 = 0.967; Reviewer B marked eight rows uncertain.
- Binary meaning-label agreement on jointly determinate rows: 0.828 (192/232), task-cluster bootstrap 95% CI [0.791, 0.866].
- Binary meaning-label Cohen's kappa: 0.659, task-cluster bootstrap 95% CI [0.595, 0.728].

## Adjudication

The existing annotation protocol defines meaning preservation strictly: the variant must preserve both the target update and all preservation constraints. This rule resolves all 48 nonmatching decisions without introducing a new outcome-based criterion.

- 192 rows required no adjudication.
- 40 conditional rows were adjudicated to 0 because `if present` adds an existence precondition absent from the base instruction.
- Eight elliptical rows were adjudicated to 0 because the text does not establish that two named peers exhaust every unrelated object and field.
- Final distribution: 80/240 meaning-preserving (all pronoun-coreference variants) and 160/240 non-preserving semantic perturbations (all conditional and elliptical variants).

## Interpretation

The prior phrase `240 meaning-preserving paraphrases` is not supported after review. The study remains useful as a natural-language specification stress test, but it must distinguish 80 validated paraphrases from 160 deliberately retained semantic-shift variants. Automated model component scores remain descriptive against the canonical executable fields; they are not evidence that all source variants preserve the base instruction.
