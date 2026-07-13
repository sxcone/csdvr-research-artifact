# Complementary Two-Agent Audit v6

Status: two AI auditors completed disjoint 120-row assignments; final human review is pending.

The auditors are AI agents, not people. Because their assignments do not overlap, this study reports coverage and outcome counts, not inter-rater agreement or Cohen's kappa.

## Main result

- Audited rows: 240.
- Accepted unchanged: 80 (0.333).
- Proposed changes: 160 (0.667).
- Ambiguous: 0.
- Proposed meaning-preservation positive rate: 0.333.
- Target object, target field, expected state, and forbidden-effect JSON: no proposed changes.
- All 160 changes affect only the meaning-preservation label: 1 -> 0.

## Systematic issues

- 80 conditional paraphrases add an object-existence precondition to the unconditional base instruction.
- 80 elliptical paraphrases protect only two named peers rather than every unrelated object and field.
- 80 pronoun-coreference paraphrases preserve both the update and global protection constraint.

These are proposed AI-audit conclusions. They must not replace the two final human reviews.
