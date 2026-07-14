# Artifact Manifest

## Primary Manuscript Evidence

| Evidence | Generator or analysis | Principal outputs |
|---|---|---|
| Paired natural-action Git study | `01_experiments/run_ase_autonomous_repair_v6.py` | `02_results/ase_autonomous_repair_raw_v6.csv`, `ase_autonomous_repair_trace_v6.jsonl`, `ase_autonomous_repair_summary_v6.csv`, `ase_autonomous_repair_error_taxonomy_v6.csv`, `ase_autonomous_repair_report_v6.md` |
| Task-cluster paired contrasts | `01_experiments/analyze_ase_paired_v6.py` | `02_results/ase_autonomous_repair_paired_contrasts_v6.csv`, `ase_autonomous_repair_paired_contrasts_v6.md` |
| Repository scaling | `01_experiments/run_ase_repository_scalability_v6.py` | `02_results/ase_repository_scalability_raw_v6.csv`, `ase_repository_scalability_summary_v6.csv`, `ase_repository_scalability_report_v6.md` |
| Independent claim audit | `01_experiments/audit_ase_revision_v6.py` | `02_results/ase_autonomous_repair_aggregate_v6.csv`, `ase_revision_numeric_audit_v6.md` |
| Submission manuscript | LaTeX source in `paper/` | `paper/main.tex`, `paper/references.bib`, `paper/Fig1.pdf`--`Fig6.pdf`, compiled preview PDF |

The v6 autonomous-repair raw file contains 1,200 policy rows derived from 240
shared initial trajectories. The scaling raw file contains 192 runs. The audit
contains 52 checks and zero recorded failures.

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
| Repository scaling | No | Yes | Re-measure local performance |
| Endpoint-backed agent studies | Yes | Yes | Regenerate model actions and recovery results |
| Paper compilation | No | Build products only | Verify manuscript rendering |
