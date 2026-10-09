# Controlled recovery comparisons (October 2026)

This folder contains portable rerun scripts and frozen protocol files for two controlled file-recovery studies reported in the C-SDVR manuscript supplement.

## Scope and outcomes

- Agent-Rollback: two public command families (cleanup and backup), each evaluated at three injected ignored-file scales. Under the pinned Git-aware inventory, the controlled runs identify a narrow recovery gap for files excluded by .gitignore. The Gitless scanner fallback is a boundary control, and selective revert plus contract-aware replay is a best-effort control.
- YoloFS: six public task scripts, paired across whole-state travel, full post-state commit, preventive path permissions, and C-SDVR projection. The results distinguish post-hoc projection from whole-state snapshot choices; preventive path permissions also satisfy the tested contracts.

These are controlled task-level comparisons, not official benchmark scores, independent deployment samples, or evidence of overall repair-rate superiority. The Agent-Rollback scales within a command family are stress-test sizes, not independent tasks. The YoloFS projection arm consumes snapshots collected by YoloFS; it does not evaluate a C-SDVR filesystem monitor.

## Reproduce

Use Linux with Python 3.11+, Git, Bash, and the pinned tools. The YoloFS arm additionally requires the YoloFS kernel module and CLI on a compatible Linux kernel. Install Agent-Rollback from its pinned source commit and expose the CLI as agent-rollback on PATH, or set AGENT_ROLLBACK_BIN.

1. From this directory, run python fetch_task_inputs.py. It retrieves only the selected task files from the pinned public YoloFS/agent-eval commit and verifies each SHA-256 hash in the frozen manifest. Third-party task source files are not bundled in this repository or in the companion Zenodo record; their source terms continue to apply.
2. Run the Agent-Rollback scripts for the cleanup and backup comparisons, the Gitless fallback control, and the selective-revert control.
3. On a compatible Linux/YoloFS setup, run python yolofs_extended_matched_replay_20261007_v2.py.

The compared Agent-Rollback source is pinned to 3bc001f1ef8a72c301da4ff1e83caddb57117ac1; the YoloFS source is pinned to 8848c243ba28ff91432c1da868671d6ed8910ed6; task inputs are pinned to 0956f8e46b31ead201e6a377f227d0cddd2419d9. The included recovery_engine.py is the exact projection/recovery adapter used in the controlled comparisons (SHA-256 recorded in the result files).

Generated result JSON files and fetched tasks_opaque inputs are ignored by Git. The Zenodo companion record contains sanitized per-case outcomes, protocols, and the input hash manifest; it excludes raw task source bytes, Base64 state snapshots, and command stdout/stderr. The historical result records preserve the original runner SHA-256 values; the public rerun scripts normalize local paths and omit source-byte snapshots from outputs.

## Archived data

The sanitized case-level results, frozen protocols, input hash manifest, and portable source snapshot are prepared for a separate Zenodo companion deposit. DOI 10.5281/zenodo.23260432 is reserved and will register after upload and publication. The earlier 40-task cohort remains a separate record (DOI 10.5281/zenodo.23190237).
