# Independent Gold-Postcondition Annotation Protocol

## Blinding and order

1. Annotators A and B work independently and must not inspect the canonical gold fields in `postcondition_paraphrase_tasks_v5.csv` or each other's sheet.
2. Each annotator fills only their assigned 240-row gold sheet. No discussion occurs before both sheets are frozen.
3. Compare `base_instruction` with `instruction`, then enter one target object, one target field, the expected state, and a JSON array of forbidden effects.
4. Set `paraphrase_preserves_meaning` to 1 only when `instruction` preserves the target update and preservation constraints in `base_instruction`; otherwise set 0 and explain why.
5. After both sheets are frozen, run `--score-gold-annotations`. Resolve only rows written to the disagreement file, with the adjudication decision documented.

## Coverage

The three variants cover pronoun coreference, conditionals with negative constraints, and elliptical multi-object preservation. The 80 base tasks span file, form, table, and micro-workflow domains.

## Agreement

Report exact normalized agreement for object, field, expected state, and forbidden-effect set; report percent agreement and Cohen's kappa for the binary meaning-preservation label. Do not replace missing labels with agreement or generate synthetic annotations.
