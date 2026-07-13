# C-SDVR Research Artifact

This private repository contains the anonymized manuscript source, experiment
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

This is an unpublished private review artifact. No public reuse license is
granted at this stage.
