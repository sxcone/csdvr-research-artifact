# Workflow Validation v4

Raw runs: 240

| Method | Runs | Success | Final residue | Intermediate deviations | Repair | Rollback | Token |
|---|---:|---:|---:|---:|---:|---:|---:|
| NoCheck | 60 | 0.050 | 0.850 | 2.22 | 0.00 | 0.00 | 600.0 |
| FinalVerifier | 60 | 1.000 | 0.000 | 2.22 | 0.95 | 0.00 | 2275.0 |
| ReflectionRetry | 60 | 0.383 | 0.517 | 2.22 | 0.00 | 0.00 | 2595.0 |
| C-SDVR | 60 | 1.000 | 0.000 | 2.15 | 2.15 | 2.15 | 1718.0 |

Per-workflow summary rows are stored in `workflow_validation_summary_v4.csv`.
Rollback-depth rows are stored in `workflow_rollback_depth_v4.csv`.
A narrative local-repair trace is stored in `workflow_case_study_v4.md`.
