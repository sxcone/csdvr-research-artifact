# AI Pre-Annotation Report v5

Status: two independent AI pre-annotations completed; human review is pending.

These outputs are drafting aids. They are not human annotations and must not be reported as such.
The two models received only the base instruction, paraphrase, domain, and phenomenon; neither received canonical gold or the other model's output.

| Alias | Model | Rows | Valid | Invalid | Mean token |
|---|---|---:|---:|---:|---:|
| Model-A | deepseek-v4-flash | 240 | 240 | 0 | 277.5 |
| Model-B | deepseek-v4-pro | 240 | 240 | 0 | 281.1 |

## AI-to-AI agreement

- target_object: n=240, agreement=1.000.
- target_field: n=240, agreement=1.000.
- expected_state: n=240, agreement=1.000.
- forbidden_effect_set: n=240, agreement=0.533.
- paraphrase_preserves_meaning: n=240, agreement=1.000, Cohen's kappa=1.000.

- Human-review rows: 240.
- Rows flagged for disagreement/invalid output: 112.
- Final human fields and reviewer initials are intentionally blank.
