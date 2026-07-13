#!/usr/bin/env python3
"""Task-cluster paired contrasts for the ASE autonomous-repair study."""

from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "02_results"
RAW = RESULTS / "ase_autonomous_repair_raw_v6.csv"
OUT = RESULTS / "ase_autonomous_repair_paired_contrasts_v6.csv"
REPORT = RESULTS / "ase_autonomous_repair_paired_contrasts_v6.md"
REFERENCE = "C-SDVR-LLMRepair"
BASELINES = (
    "NoCheck",
    "FinalReplay",
    "JudgeRepair",
    "C-SDVR-OracleUpperBound",
)
METRICS = (
    ("final_success", 1.0, "success difference"),
    ("final_residue", -1.0, "residue reduction"),
    ("integrity_preserving_outcome", 1.0, "integrity-outcome difference"),
    ("token_cost", -1.0, "token saving"),
)
BOOTSTRAPS = 10_000
SEED = 20_260_714


def number(value: str) -> float:
    if value == "True":
        return 1.0
    if value == "False":
        return 0.0
    return float(value)


def percentile(sorted_values: list[float], probability: float) -> float:
    index = round((len(sorted_values) - 1) * probability)
    return sorted_values[index]


def stable_float(value: float) -> str:
    """Serialize computed statistics identically across supported Python versions."""
    return f"{value:.12f}"


def main() -> None:
    with RAW.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    indexed = {(row["trajectory_id"], row["policy"]): row for row in rows}
    trajectories = sorted({row["trajectory_id"] for row in rows})
    task_for = {
        trajectory: indexed[(trajectory, "NoCheck")]["task_id"]
        for trajectory in trajectories
    }
    tasks = sorted(set(task_for.values()))
    if len(tasks) != 40 or len(trajectories) != 240:
        raise AssertionError("Expected 40 tasks and 240 paired trajectories")

    output: list[dict[str, str | int | float]] = []
    for baseline_index, baseline in enumerate(BASELINES):
        for metric_index, (field, direction, label) in enumerate(METRICS):
            by_task: dict[str, list[float]] = defaultdict(list)
            for trajectory in trajectories:
                reference = number(indexed[(trajectory, REFERENCE)][field])
                comparator = number(indexed[(trajectory, baseline)][field])
                by_task[task_for[trajectory]].append(direction * (reference - comparator))
            task_means = {
                task: math.fsum(values) / len(values) for task, values in by_task.items()
            }
            estimate = math.fsum(task_means.values()) / len(tasks)
            rng = random.Random(SEED + baseline_index * 100 + metric_index)
            bootstrap_values = sorted(
                math.fsum(task_means[rng.choice(tasks)] for _ in tasks) / len(tasks)
                for _ in range(BOOTSTRAPS)
            )
            output.append(
                {
                    "reference_policy": REFERENCE,
                    "baseline_policy": baseline,
                    "metric": field,
                    "effect_label": label,
                    "positive_favors_reference": 1,
                    "task_clusters": len(tasks),
                    "paired_trajectories": len(trajectories),
                    "estimate": stable_float(estimate),
                    "ci95_low": stable_float(percentile(bootstrap_values, 0.025)),
                    "ci95_high": stable_float(percentile(bootstrap_values, 0.975)),
                    "bootstrap_resamples": BOOTSTRAPS,
                    "seed": SEED + baseline_index * 100 + metric_index,
                }
            )

    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)

    lines = [
        "# ASE Paired Task-Cluster Contrasts v6",
        "",
        "Positive values favor C-SDVR-LLMRepair. Intervals use 10,000 paired "
        "bootstrap resamples over 40 task clusters; the six model/repeat trajectories "
        "within each task are averaged before resampling.",
        "",
        "| Baseline | Effect | Estimate | 95% task-cluster CI |",
        "|---|---|---:|---:|",
    ]
    for row in output:
        lines.append(
            f"| {row['baseline_policy']} | {row['effect_label']} | "
            f"{float(row['estimate']):.4f} | "
            f"[{float(row['ci95_low']):.4f}, {float(row['ci95_high']):.4f}] |"
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT)
    print(REPORT)


if __name__ == "__main__":
    main()
