# C-SDVR Research Artifact

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21359453.svg)](https://doi.org/10.5281/zenodo.21359453)

## ASE submission dataset: V8.10

The 40-task cohort tables reported in “C-SDVR: Action Semantics for Contract-Aware Recovery in Repository Agents” are archived as a separate, data-only Zenodo record: [C-SDVR V8.10 cohort tables](https://doi.org/10.5281/zenodo.23190237).

The record contains ESM_2.csv (800 paired task-policy-cap rows), ESM_3.csv (40 task-level summaries), a data dictionary, a README, and SHA-256 checksums. The rows are repeated comparisons over 40 task units and are conditional on the supplied contracts and the reported model/protocol stratum.

This dataset DOI identifies the tables and documentation only. It does not archive the V8.10 controller, cohort-generation or replay pipeline, proposal pools, raw model histories, selected execution receipts, cumulative usage ledger, annotation forms, or packet-distribution records; the dataset alone does not enable a full end-to-end rerun. The Zenodo record carries an All rights reserved statement for the deposited author-prepared files; third-party benchmark material remains subject to its source terms.

This ASE submission dataset is a separate version track from the software and evidence artifacts cited by this repository's existing DOI badge and CITATION.cff. The new dataset DOI does not replace or extend those release identifiers.

This public repository contains the manuscript source, experiment
code, raw records, derived tables, and numeric audits for:

> **C-SDVR: Cost-Aware Runtime Verification and Local Recovery for
> Side-Effectful Software Engineering Agents**

C-SDVR compares scoped pre/post state, checks executable postconditions, and
selects continuation, model-generated local repair, guarded rollback, or safe
stop. The work studies observable and reversible file, form, record, workflow,
and local Git-repository effects. It does **not** claim open-world safety or
correct recovery for irreversible external actions.

## Headline Evidence

The principal paired Git study uses 40 synthetic repository tasks, two
DeepSeek configurations, three repeats, 240 natural action trajectories, and
five policy replays per trajectory (1,200 policy rows). Of 21 naturally failing
initial trajectories, nine leave residue. The reported aggregate results are:

| Policy | Success | Residue | Integrity-preserving outcome | Mean tokens |
|---|---:|---:|---:|---:|
| C-SDVR-LLMRepair | 236/240 (0.9833) | 0/240 (0.0000) | 240/240 (1.0000) | 578.9 |
| FinalReplay | 227/240 (0.9458) | 4/240 (0.0167) | 227/240 (0.9458) | 562.6 |
| JudgeRepair | 216/240 (0.9000) | 13/240 (0.0542) | 216/240 (0.9000) | 1253.0 |
| NoCheck | 219/240 (0.9125) | 9/240 (0.0375) | 219/240 (0.9125) | 497.9 |
| C-SDVR-OracleUpperBound | 240/240 (1.0000) | 0/240 (0.0000) | 240/240 (1.0000) | 497.9 |

The autonomous C-SDVR policy repairs 17/21 initial failures, removes all 9/9
observed residue cases, and safely stops on four unrepaired tasks. A separate
192-run scaling study measures snapshot, semantic-diff, verification, and
rollback cost across repository size and mutation width. See
`02_results/ase_revision_numeric_audit_v6.md` for the machine-checkable
52-claim audit.

## Repository Layout

- `paper/`: Springer `sn-jnl` LaTeX source, bibliography, figures, and compiled
  Automated Software Engineering submission preview.
- `01_experiments/`: experiment generators, endpoint-backed agent studies,
  paired analysis, and independent numeric-audit scripts.
- `02_results/`: raw CSV/JSONL records, summaries, reports, and figure inputs.
- `ARTIFACT_MANIFEST.md`: primary versus supplemental evidence map.
- `DATA_DICTIONARY.md`: schemas and interpretation notes for the main v6 data.

Historical review letters, author working notes, LaTeX build products, archive
copies, credentials, and local machine metadata are intentionally excluded.

## Requirements

- Python 3.11 or newer
- Git
- A LaTeX distribution for rebuilding the paper
- An OpenAI-compatible endpoint only when regenerating endpoint-backed results

Install the Python packages in an isolated environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Offline Verification

The main statistical contrasts and numeric audit can be regenerated from the
committed raw data without an API key or network access:

```bash
python 01_experiments/analyze_ase_paired_v6.py
python 01_experiments/audit_ase_revision_v6.py
```

Expected audit result: `Checks: 52` and `Failures: 0` in
`02_results/ase_revision_numeric_audit_v6.md`.

The repository-scaling benchmark is also local and reversible:

```bash
python 01_experiments/run_ase_repository_scalability_v6.py --smoke
python 01_experiments/run_ase_repository_scalability_v6.py
```

## Endpoint-Backed Reproduction

Copy `.env.example` to a local ignored file or export the variables in the
shell. Never write a real key into a tracked file.

```bash
export CSDVR_LLM_BASE_URL=https://api.deepseek.com/v1
export CSDVR_LLM_MODEL_A=deepseek-v4-flash
export CSDVR_LLM_MODEL_B=deepseek-v4-pro
export CSDVR_LLM_API_KEY='<your-key>'
export CSDVR_ASE_REPEATS=3
export CSDVR_ASE_TEMPERATURE=0.7

python 01_experiments/run_ase_autonomous_repair_v6.py --smoke
python 01_experiments/run_ase_autonomous_repair_v6.py
```

The full command makes paid endpoint calls and overwrites the corresponding
v6 result files. The smoke run is for connectivity and schema validation only;
smoke outputs are not manuscript evidence. Model availability and aliases are
endpoint-specific, so record any substitutions when reproducing the study.

## Paper Build

From `paper/`, build the working preview with a current TeX Live/MacTeX setup:

```bash
latexmk -pdf main.tex
```

The committed preview is
`paper/C-SDVR_Automated_Software_Engineering_submission_preview.pdf`.

## Citation

The artifact is maintained by Xiuchi Sun, School of Mathematics, Southwest
Jiaotong University. ORCID:
[0009-0007-5812-3870](https://orcid.org/0009-0007-5812-3870).

Citation metadata are provided in `CITATION.cff`. For reproducibility, cite the
immutable Zenodo `v1.0.0` release using version DOI
[`10.5281/zenodo.21359453`](https://doi.org/10.5281/zenodo.21359453). The
all-version record is available under concept DOI
[`10.5281/zenodo.21359452`](https://doi.org/10.5281/zenodo.21359452).

## Integrity and Scope

- Initial actions are shared across all five policy replays within each paired
  trajectory; policy comparisons do not resample the initial action.
- Invalid JSON, execution errors, residue, safe stops, and repair-induced side
  effects remain explicit fields rather than being silently converted to
  success.
- Task-cluster bootstrap intervals use 40 task clusters rather than treating
  repeated runs as independent tasks.
- The tasks and human-reviewed language variants are synthetic and contain no
  personal, clinical, or third-party restricted data.
- External publication, payment, email, production deployment, and other
  non-compensable effects are outside the evaluated scope.

The repository's current source tree has no blanket public reuse license.
Rights for individual archived versions are determined by their respective
records. The separate V8.10 dataset record uses the rights statement in its
Zenodo metadata; third-party content remains subject to its source terms.
