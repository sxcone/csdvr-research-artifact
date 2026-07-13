# Natural-language postcondition study v5

Status: endpoint generation completed for 2 model(s); independent human annotation is pending.

- Generated rows: 480.
- Thinking mode: disabled; sampling temperature: 0.2.
- Raw and parsed endpoint outputs are retained; API credentials are not stored.
- Automated component scores use the canonical task fields and explicit preservation clauses.
- Model-to-model equality is strict representation-level agreement and is not human annotation.
- Automated scores remain provisional until two annotators complete the A/B sheets.

| Model | Phenomenon | n | Object | Field | Constraint | Forbidden recall | Invalid JSON | Token |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Model-A | conditional_negative_constraint | 80 | 1.000 | 1.000 | 1.000 | 0.600 | 0.000 | 153.6 |
| Model-A | ellipsis_multi_object_preservation | 80 | 0.775 | 0.775 | 0.775 | 1.000 | 0.000 | 166.3 |
| Model-A | pronoun_coreference | 80 | 1.000 | 1.000 | 1.000 | 0.344 | 0.000 | 159.2 |
| Model-B | conditional_negative_constraint | 80 | 0.875 | 0.887 | 1.000 | 0.981 | 0.000 | 157.1 |
| Model-B | ellipsis_multi_object_preservation | 80 | 0.762 | 0.762 | 0.787 | 1.000 | 0.000 | 167.5 |
| Model-B | pronoun_coreference | 80 | 1.000 | 1.000 | 1.000 | 0.400 | 0.000 | 164.9 |

## Strict model-to-model representation agreement

- object_match: 0.946.
- field_match: 0.950.
- expected_state_match: 0.704.
- forbidden_effects_match: 0.312.
- exact_postcondition_match: 0.150.
