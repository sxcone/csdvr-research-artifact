# Artifact Manifest

## Primary Manuscript Evidence

| Evidence | Generator or analysis | Principal outputs |
|---|---|---|
| Paired natural-action Git study | `01_experiments/run_ase_autonomous_repair_v6.py` | `02_results/ase_autonomous_repair_raw_v6.csv`, `ase_autonomous_repair_trace_v6.jsonl`, `ase_autonomous_repair_summary_v6.csv`, `ase_autonomous_repair_error_taxonomy_v6.csv`, `ase_autonomous_repair_report_v6.md` |
| Task-cluster paired contrasts | `01_experiments/analyze_ase_paired_v6.py` | `02_results/ase_autonomous_repair_paired_contrasts_v6.csv`, `ase_autonomous_repair_paired_contrasts_v6.md` |
| Task influence and recovery decomposition | `01_experiments/analyze_ase_task_influence_v7.py` | `02_results/ase_task_level_effects_v7.csv`, `ase_leave_one_task_out_v7.csv`, `ase_error_type_outcomes_v7.csv`, `ase_action_diversity_v7.csv`, `ase_recovery_decomposition_v7.csv`, `ase_task_influence_report_v7.md` |
| Identical-repair rollback counterfactual | `01_experiments/run_ase_counterfactual_replay_v7.py` | `02_results/ase_counterfactual_rollback_raw_v7.csv`, `ase_counterfactual_rollback_summary_v7.csv`, `ase_counterfactual_rollback_paired_v7.csv`, `ase_hidden_check_dependence_v7.csv`, `ase_counterfactual_replay_report_v7.md` |
| Strict controlled rollback ablation | `01_experiments/run_strict_rollback_ablation_v7.py` | `02_results/strict_rollback_ablation_raw_v7.csv`, `strict_rollback_ablation_summary_v7.csv`, `strict_rollback_ablation_paired_v7.csv`, `strict_rollback_ablation_report_v7.md` |
| Matched-action full-reset counterfactual | `01_experiments/run_ase_counterfactual_full_reset_v8.py` | `02_results/ase_counterfactual_three_way_raw_v8.csv`, `ase_counterfactual_three_way_summary_v8.csv`, `ase_counterfactual_three_way_paired_v8.csv`, `ase_counterfactual_three_way_report_v8.md` |
| Counterfactual uncertainty analysis | `01_experiments/analyze_counterfactual_uncertainty_v9.py` | `02_results/ase_counterfactual_uncertainty_v9.csv`, `ase_counterfactual_uncertainty_report_v9.md` |
| Oracle-equivalence audit | `01_experiments/audit_oracle_equivalence_v10.py` | `02_results/ase_oracle_equivalence_audit_v10.csv`, `ase_oracle_equivalence_audit_report_v10.md` |
| Repository scaling | `01_experiments/run_ase_repository_scalability_v6.py` | `02_results/ase_repository_scalability_raw_v6.csv`, `ase_repository_scalability_summary_v6.csv`, `ase_repository_scalability_report_v6.md` |
| Independent claim audit | `01_experiments/audit_ase_revision_v6.py` | `02_results/ase_autonomous_repair_aggregate_v6.csv`, `ase_revision_numeric_audit_v6.md` |
| Specialist-review sensitivity analysis | `01_experiments/analyze_specialist_review_sensitivity_v12.py` | `02_results/specialist_review_sensitivity_v12.csv`, `specialist_review_sensitivity_v12.md` |
| Auxiliary-change contract stress | `01_experiments/run_auxiliary_change_stress_v16.py` | `02_results/auxiliary_change_stress_raw_v16.csv`, `auxiliary_change_stress_summary_v16.csv`, `auxiliary_change_stress_report_v16.md` |
| Matched-evidence LLM restoration replay | `01_experiments/run_ase_matched_no_rollback_v17.py`, `analyze_matched_no_rollback_v17.py` | `02_results/matched_norollback_raw_v17.csv`, `matched_norollback_summary_v17.csv`, `matched_norollback_paired_v17.csv`, `matched_norollback_task_clusters_v17.csv`, `matched_norollback_statistics_v17.csv`, `matched_norollback_report_v17.md`, `matched_norollback_analysis_report_v17.md` |
| Submission-wide audits | `01_experiments/audit_sqj_submission_v16.py`, `audit_sqj_submission_v17.py` | `02_results/sqj_submission_numeric_audit_v16.md`, `sqj_submission_numeric_audit_v17.md` |
| Closed-loop Figure 1 | `01_experiments/generate_closed_loop_figure_v15.py` | `paper/Figure1.pdf` |
| Submission manuscript | LaTeX source in `paper/` | `paper/main.tex`, `paper/C-SDVR_SQJ_revised_v17.tex`, `paper/references.bib`, figures, and `paper/C-SDVR_SQJ_revised_v17.pdf` |
| Submission self-audit | Manual traceability, review disposition, and PDF comparison | `top_paper_checklist_q1_q15_v17.md`, `02_results/round9_review_revision_response_v17.md`, `02_results/sqj_page_comparison_v17.md` |
| Independent human contract/verifier audit and v18 closure | Independent human review of all 12 blinded tasks; v18 corrections and re-audit close B08, B10, B11, and B12; AI-assisted wording/formatting only | v17 frozen package plus `02_results/contract_verifier_audit_adjudication_v18.csv`, `contract_verifier_external_reviewer_consolidated_v18.xlsx`, `contract_verifier_external_reviewer_reaudit_filled_v18.xlsx`, `contract_verifier_independent_audit_report_v18.md`, and `contract_verifier_reviewer_declaration_v18.txt` |
| v17 integrity manifest | SHA-256 checksum generation | `SHA256SUMS_v17.txt` |
| v18 artifact-only integrity manifest | SHA-256 checksum generation for the public artifact update; the manuscript directory is intentionally excluded from this release | `SHA256SUMS_ARTIFACT_v18.txt` |

The v6 autonomous-repair raw file contains 1,200 policy rows derived from 240
shared initial trajectories. The v7 counterfactual contains 42 paired
candidate executions over the 21 natural failures, and the strict controlled
ablation contains 24,000 rows. The scaling raw file contains 192 runs. Both
the original 52-check audit and the submission-wide major-revision audit record
zero failures. The current manuscript snapshot is
`paper/C-SDVR_SQJ_revised_v17.pdf`; its v17 audit contains 141 checks. The v16
revision defines verifier-certified harmful-change sets and minimum restoration
scope, repositions P1--P3 around three failure modes, tests the allowed-effect
contract boundary, restricts the Git comparison to system-level evidence,
exposes the independent-audit gap, and retains a
37-page SQJ-aligned structure.

The v17 matched-evidence replay contains 480 policy rows for the same 240
archived trajectories. Its two branches share the dirty-state, repair-prompt,
and repair-action hashes; 21 initial failures each receive one shared repair
call. The analysis reports 235/240 success and 1/240 residue for
`Matched-CSDVR`, versus 228/240 and 8/240 for `Matched-NoRollback`. The
trajectory-level exact paired test is descriptive because the failures occupy
nine task clusters; the equal-cluster sign test is `p=0.125`.

The independent contract/verifier audit covers 12 blinded tasks. An
independent human reviewer made the technical ratings and decisions before
model, policy, failure, residue, or outcome data were revealed. The frozen v17
record contained eight Pass decisions and four Major Revise findings
(`B08`, `B10`, `B11`, and `B12`). The v18 package preserves the corrected
contracts, deterministic local rechecks, and the independent human re-audit;
all four revised items received Pass decisions. The final technical
disposition is therefore 12/12 Pass, with no changed success, residue, or
restoration-scope classification in the affected-task recheck. ChatGPT
assistance was limited to wording, formatting, and clerical editing and did
not determine or change any technical rating.

## Supporting Evidence

The remaining scripts and result files support the manuscript's controlled
benchmark, local file/form/browser checks, workflow validation, boundary
conditions, postcondition generation and paraphrase analyses, endpoint
compatibility studies, cost sensitivity, and figure generation. Version
suffixes preserve the evolution of these studies; the manuscript identifies
which strata are principal, supporting, or exploratory.

## Intentionally Excluded

- API credentials and `.env` files
- Reviewer reports, response drafts, and private author notes
- Local terminal logs that expose credentials and machine metadata
- LaTeX intermediate files and temporary execution directories
- Redundant archive copies and large publication-format TIFF duplicates

## Reproduction Classes

| Class | Network/API required | May overwrite committed results | Intended use |
|---|---:|---:|---|
| Paired analysis and numeric audit | No | Yes, deterministically | Verify manuscript claims from raw records |
| Strict rollback ablation and task influence | No | Yes, deterministically | Isolate rollback and audit task concentration |
| Identical-repair counterfactual replay | No | Yes, deterministically | Replay archived actions under matched recovery |
| Repository scaling | No | Yes | Re-measure local performance |
| Auxiliary-change contract stress | No | Yes, deterministically | Test the authored allowed-effect boundary |
| Matched-evidence restoration analysis | No | Yes, deterministically | Verify paired hashes, exact contrasts, and task-cluster diagnostics from v17 raw records |
| Endpoint-backed agent studies | Yes | Yes | Regenerate model actions and recovery results |
| Paper compilation | No | Build products only | Verify manuscript rendering |
