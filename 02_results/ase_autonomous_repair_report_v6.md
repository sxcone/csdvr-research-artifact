# ASE Paired Autonomous-Repair Validation v6

Smoke mode: False
Natural LLM trajectories: 240
Policy replay rows: 1200
Initial failed trajectories: 21
Initial trajectories with harmful residue: 9
Each initial action was sampled once and replayed unchanged across all policies; no post-hoc fault was injected.
C-SDVR-OracleUpperBound is explicitly a scripted upper bound. C-SDVR-LLMRepair uses model-generated repair actions and guarded state restoration.
JudgeRepair receives the same write/delete/rename interface and one repair call, addressing the earlier action-permission asymmetry.
All repositories are synthetic local Git repositories; no external repository is mutated.

| Model | Policy | Rows | Final success | Final residue | Integrity outcome | Safe stop | Repair success | Repair side effect | Token cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek-v4-flash | C-SDVR-LLMRepair | 120 | 1.000 | 0.000 | 1.000 | 0.000 | 0.067 | 0.000 | 553.6 |
| deepseek-v4-flash | C-SDVR-OracleUpperBound | 120 | 1.000 | 0.000 | 1.000 | 0.000 | 0.067 | 0.000 | 492.9 |
| deepseek-v4-flash | FinalReplay | 120 | 0.958 | 0.008 | 0.958 | 0.000 | 0.025 | 0.000 | 537.6 |
| deepseek-v4-flash | JudgeRepair | 120 | 0.925 | 0.033 | 0.925 | 0.000 | 0.033 | 0.008 | 1162.6 |
| deepseek-v4-flash | NoCheck | 120 | 0.933 | 0.025 | 0.933 | 0.000 | 0.000 | 0.000 | 492.9 |
| deepseek-v4-pro | C-SDVR-LLMRepair | 120 | 0.967 | 0.000 | 1.000 | 0.033 | 0.075 | 0.000 | 604.2 |
| deepseek-v4-pro | C-SDVR-OracleUpperBound | 120 | 1.000 | 0.000 | 1.000 | 0.000 | 0.108 | 0.000 | 502.8 |
| deepseek-v4-pro | FinalReplay | 120 | 0.933 | 0.025 | 0.933 | 0.000 | 0.042 | 0.000 | 587.5 |
| deepseek-v4-pro | JudgeRepair | 120 | 0.875 | 0.075 | 0.875 | 0.000 | 0.108 | 0.033 | 1343.4 |
| deepseek-v4-pro | NoCheck | 120 | 0.892 | 0.050 | 0.892 | 0.000 | 0.000 | 0.000 | 502.8 |

## Natural error taxonomy

| Model | Category | Error type | Count |
|---|---|---|---:|
| deepseek-v4-flash | build | none | 9 |
| deepseek-v4-flash | ci | none | 6 |
| deepseek-v4-flash | ci-security | extra_side_effect | 1 |
| deepseek-v4-flash | ci-security | none | 5 |
| deepseek-v4-flash | compiler-configuration | none | 3 |
| deepseek-v4-flash | configuration | none | 9 |
| deepseek-v4-flash | configuration-migration | none | 6 |
| deepseek-v4-flash | dependency | extra_side_effect | 1 |
| deepseek-v4-flash | dependency | none | 5 |
| deepseek-v4-flash | executable-code-repair | none | 25 |
| deepseek-v4-flash | executable-code-repair | wrong_content | 5 |
| deepseek-v4-flash | multi-file-configuration | none | 3 |
| deepseek-v4-flash | release-maintenance | none | 6 |
| deepseek-v4-flash | repository-hygiene | none | 3 |
| deepseek-v4-flash | rule-based-configuration | none | 9 |
| deepseek-v4-flash | source-maintenance | extra_side_effect | 1 |
| deepseek-v4-flash | source-maintenance | none | 14 |
| deepseek-v4-flash | test-configuration | none | 3 |
| deepseek-v4-flash | tooling | none | 6 |
| deepseek-v4-pro | build | none | 9 |
| deepseek-v4-pro | ci | none | 6 |
| deepseek-v4-pro | ci-security | extra_side_effect | 1 |
| deepseek-v4-pro | ci-security | none | 5 |
| deepseek-v4-pro | compiler-configuration | none | 3 |
| deepseek-v4-pro | configuration | none | 9 |
| deepseek-v4-pro | configuration-migration | extra_side_effect | 1 |
| deepseek-v4-pro | configuration-migration | none | 5 |
| deepseek-v4-pro | dependency | extra_side_effect | 2 |
| deepseek-v4-pro | dependency | none | 4 |
| deepseek-v4-pro | executable-code-repair | non_persistence | 1 |
| deepseek-v4-pro | executable-code-repair | none | 23 |
| deepseek-v4-pro | executable-code-repair | wrong_content | 6 |
| deepseek-v4-pro | multi-file-configuration | none | 3 |
| deepseek-v4-pro | release-maintenance | none | 6 |
| deepseek-v4-pro | repository-hygiene | none | 3 |
| deepseek-v4-pro | rule-based-configuration | none | 9 |
| deepseek-v4-pro | source-maintenance | extra_side_effect | 2 |
| deepseek-v4-pro | source-maintenance | none | 13 |
| deepseek-v4-pro | test-configuration | none | 3 |
| deepseek-v4-pro | tooling | none | 6 |
