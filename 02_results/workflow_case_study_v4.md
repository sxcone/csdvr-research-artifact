# Workflow Case Study v4

This trace uses the `student_records` workflow to show how local recovery prevents error accumulation.

| Step | Operation | Injected fault | Detected | Problem | C-SDVR action | Rollback scope |
|---:|---|---|---|---|---|---:|
| 1 | create_student | none | False | none | continue | 0 |
| 2 | edit_field | extra_side_effect | True | extra_side_effect | local rollback + bounded repair | 4 |
| 3 | edit_field | wrong_field | True | target_unsatisfied | local rollback + bounded repair | 4 |
| 4 | delete_student | none | False | none | continue | 0 |
| 5 | export_csv | non_persistence | True | target_unsatisfied | local rollback + bounded repair | 4 |
| 6 | consistency_check | none | False | none | continue | 0 |

FinalVerifier comparison: the final-only policy detects failure at workflow end, restores the initial snapshot, and replays all six steps. This is intentionally strong because it assumes a full-workflow snapshot and a clean replay plan.
C-SDVR final success/residue: True/False.
Final full-replay success/residue: True/False.
Interpretation: C-SDVR does not need to replay unaffected steps; it restores only the pre-step scoped state and repairs the bounded target.
