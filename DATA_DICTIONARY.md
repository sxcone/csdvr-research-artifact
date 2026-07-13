# Data Dictionary

This document describes the principal v6 evidence used in the submission. CSV
files are UTF-8 with one header row. Boolean values are serialized as
`True`/`False`; rates in summary files are proportions in `[0,1]`. Token counts
are endpoint-reported when available and estimated only where explicitly
identified by the producing script.

## `ase_autonomous_repair_raw_v6.csv`

One row is one policy replay of a shared initial model action. The unit used for
paired inference is the task cluster, not the individual policy row.

| Field group | Columns | Meaning |
|---|---|---|
| Pairing keys | `trajectory_id`, `task_id`, `category`, `model`, `repeat`, `policy` | Identify the shared action trajectory and replay policy. Each trajectory has exactly five policy rows. |
| Initial outcome | `initial_success`, `initial_target_satisfied`, `initial_residue`, `initial_error_type`, `initial_exec_ok`, `initial_exec_error` | Exact evaluation of the model's first action before policy-specific recovery. |
| Changed state | `initial_changed_paths`, `initial_semantic_changed_paths`, `initial_residue_paths` | Serialized scoped path sets derived from repository snapshots and semantic comparison. |
| Final outcome | `final_success`, `final_target_satisfied`, `final_residue`, `final_residue_paths` | Exact post-recovery task and residue evaluation. A safe stop can preserve integrity while final success remains false. |
| Integrity and control | `integrity_preserving_outcome`, `safe_stop`, `repair_trigger`, `rollback_trigger`, `repair_success`, `unnecessary_repair`, `repair_induced_side_effect` | Policy decisions and their verified effects. |
| Judge diagnostics | `judge_false_success`, `judge_false_alarm`, `invalid_judge_json`, `judge_hash`, `judge_json` | Judge behavior and parse validity; invalid output is never silently counted as success. |
| Rollback scope | `rollback_paths`, `rollback_bytes` | Restored path count/list representation and bytes restored by scoped rollback. |
| Cost | `token_cost`, `call_count`, `wall_clock_ms` | Model-token, request-count, and elapsed-time records for the replay. |
| Parse validity | `invalid_initial_json`, `invalid_repair_json` | Whether initial or repair model output failed JSON/schema validation. |
| Action provenance | `initial_action_hash`, `initial_action_json`, `repair_action_hash`, `repair_action_json`, `repair_exec_error` | Canonicalized action records, hashes, and execution error. |
| State provenance | `before_state_hash`, `post_state_hash`, `final_state_hash` | Hashes used to verify shared initial state/action and policy-specific final state. |
| Protocol metadata | `oracle_version`, `action_prompt_version`, `judge_prompt_version`, `sampling_temperature`, `endpoint_host`, `request_started_utc` | Reproduction and endpoint metadata; no credential is stored. |

Expected invariants:

- 1,200 rows, 40 tasks, two models, three repeats, and five policies.
- 240 distinct `trajectory_id` values.
- All five rows for a trajectory share `initial_action_hash`,
  `post_state_hash`, and initial outcome fields.
- The oracle policy is an upper bound and is not interpreted as autonomous.

## `ase_autonomous_repair_summary_v6.csv`

Aggregates outcomes by model and policy. It reports run count, initial and final
success, target satisfaction, residue, state integrity, safe stop, recovery
triggers and outcomes, judge errors, parse validity, calls, tokens, and latency.
The exact schema is generated directly from the raw file by the experiment
script.

## `ase_autonomous_repair_paired_contrasts_v6.csv`

| Column | Meaning |
|---|---|
| `reference_policy` | Always `C-SDVR-LLMRepair`. |
| `baseline_policy` | Comparator policy. |
| `metric` | Success, residue, integrity outcome, or token cost. |
| `effect_label` | Human-readable effect direction. |
| `positive_favors_reference` | `1`; estimates are oriented so positive values favor C-SDVR. |
| `task_clusters` | Number of task-level clusters (`40`). |
| `paired_trajectories` | Number of shared initial trajectories (`240`). |
| `estimate` | Mean paired task-cluster effect. |
| `ci95_low`, `ci95_high` | Percentile 95% task-cluster bootstrap interval. |
| `bootstrap_resamples` | Number of resamples (`10000`). |

## `ase_repository_scalability_raw_v6.csv`

One row is one local synthetic-repository measurement.

| Field group | Columns | Meaning |
|---|---|---|
| Design | `repository_files`, `file_size_bytes`, `mutation_width`, `repeat` | Repository size, generated file size, number of mutated files, and repetition. |
| Timing | `snapshot_ms`, `mutation_ms`, `post_hash_ms`, `diff_ms`, `verification_ms`, `rollback_ms`, `final_hash_ms`, `total_control_ms` | Wall-clock components measured with the local monotonic clock. |
| Volume | `snapshot_bytes`, `changed_bytes`, `rollback_bytes`, `diff_entries` | State and rollback volume. |
| Correctness | `verification_correct`, `rollback_success`, `state_hash` | Exact-diff result, clean restoration result, and final state identity. |

Expected invariants: 192 rows covering four repository sizes, two file sizes,
three mutation widths, and eight repetitions per design cell. All exact-diff
and rollback assertions must pass.

## Trace JSONL

`ase_autonomous_repair_trace_v6.jsonl` stores detailed per-run action and state
evidence corresponding to the CSV. It supports audit and error analysis; it
does not contain API keys. Hash fields permit equality and provenance checks
without treating a model's textual self-report as verification.
