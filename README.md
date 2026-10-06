# C-SDVR experiment code

This repository contains experiment execution scripts, data-generation and analysis code, the synthetic task input required by the executable benchmark, dependency configuration, and an endpoint environment template.

## Contents

- 01_experiments/: controlled benchmarks, model-backed runs, validation workflows, and analysis scripts.
- 01_experiments/tasks_executable_v3.csv: synthetic task definitions consumed by the executable benchmark.
- requirements.txt: Python dependencies.
- .env.example: placeholder configuration for endpoint-backed experiments.
- .github/workflows/verify.yml: syntax validation for experiment scripts.

## Local setup

Use Python 3.11 or newer. Create an isolated environment and install the listed dependencies:

    python -m venv .venv
    python -m pip install -r requirements.txt

Example local runs:

    python 01_experiments/run_executable_benchmark.py
    python 01_experiments/run_ase_repository_scalability_v6.py --smoke

Endpoint-backed scripts read the variables shown in .env.example. Configure real credentials only in an ignored local .env file or in the shell. Such runs may send requests to a paid model endpoint.

Generated tables, logs, and figures are written under 02_results/ and are excluded from version control. The synthetic task input remains tracked so the executable benchmark can run from a fresh checkout.
