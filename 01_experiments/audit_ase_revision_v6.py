#!/usr/bin/env python3
"""Independent row-count and metric audit for the ASE v6 revision evidence."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "02_results"
AUTONOMOUS_RAW = RESULTS / "ase_autonomous_repair_raw_v6.csv"
AUTONOMOUS_SUMMARY = RESULTS / "ase_autonomous_repair_summary_v6.csv"
SCALE_RAW = RESULTS / "ase_repository_scalability_raw_v6.csv"
PAIRED_CONTRASTS = RESULTS / "ase_autonomous_repair_paired_contrasts_v6.csv"
AGGREGATE = RESULTS / "ase_autonomous_repair_aggregate_v6.csv"
AUDIT = RESULTS / "ase_revision_numeric_audit_v6.md"


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append((name, bool(condition), detail))

    rows = read_csv(AUTONOMOUS_RAW)
    check("autonomous row count", len(rows) == 1200, f"observed={len(rows)}, expected=1200")
    policies = sorted({row["policy"] for row in rows})
    models = sorted({row["model"] for row in rows})
    tasks = sorted({row["task_id"] for row in rows})
    repeats = sorted({int(row["repeat"]) for row in rows})
    check("policy count", len(policies) == 5, f"observed={policies}")
    check("model count", len(models) == 2, f"observed={models}")
    check("task count", len(tasks) == 40, f"observed={len(tasks)}")
    check("repeat indices", repeats == [0, 1, 2], f"observed={repeats}")

    trajectory_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        trajectory_rows[row["trajectory_id"]].append(row)
    check("trajectory count", len(trajectory_rows) == 240, f"observed={len(trajectory_rows)}")
    check(
        "five policy replays per trajectory",
        all(len(values) == 5 and {value["policy"] for value in values} == set(policies) for values in trajectory_rows.values()),
        "each trajectory must contain every policy exactly once",
    )
    check(
        "shared initial action per trajectory",
        all(len({value["initial_action_hash"] for value in values}) == 1 for values in trajectory_rows.values()),
        "initial action hashes are identical across policy replay rows",
    )
    check(
        "shared post-action state per trajectory",
        all(len({value["post_state_hash"] for value in values}) == 1 for values in trajectory_rows.values()),
        "post-action state hashes are identical across policy replay rows",
    )
    check(
        "shared initial outcomes per trajectory",
        all(
            len({(value["initial_success"], value["initial_residue"], value["initial_error_type"]) for value in values}) == 1
            for values in trajectory_rows.values()
        ),
        "initial success, residue, and taxonomy labels are policy invariant",
    )

    base_rows = [values[0] for values in trajectory_rows.values()]
    initial_failures = sum(not as_bool(row["initial_success"]) for row in base_rows)
    initial_residue = sum(as_bool(row["initial_residue"]) for row in base_rows)
    check("natural initial failures", initial_failures == 21, f"observed={initial_failures}, expected=21")
    check("natural residue trajectories", initial_residue == 9, f"observed={initial_residue}, expected=9")
    check(
        "no invalid initial JSON",
        sum(as_bool(row["invalid_initial_json"]) for row in base_rows) == 0,
        "all initial action objects passed JSON/schema parsing",
    )

    counts = Counter((row["model"], row["policy"]) for row in rows)
    check(
        "balanced model-policy cells",
        all(count == 120 for count in counts.values()) and len(counts) == 10,
        f"cells={dict(sorted(counts.items()))}",
    )

    aggregate_rows: list[dict[str, Any]] = []
    for policy in policies:
        values = [row for row in rows if row["policy"] == policy]
        failed = [row for row in values if not as_bool(row["initial_success"])]
        residue_cases = [row for row in values if as_bool(row["initial_residue"])]
        aggregate_rows.append(
            {
                "policy": policy,
                "policy_rows": len(values),
                "unique_trajectories": len({row["trajectory_id"] for row in values}),
                "initial_success": mean(as_bool(row["initial_success"]) for row in values),
                "initial_residue": mean(as_bool(row["initial_residue"]) for row in values),
                "final_success": mean(as_bool(row["final_success"]) for row in values),
                "final_residue": mean(as_bool(row["final_residue"]) for row in values),
                "integrity_preserving_outcome": mean(as_bool(row["integrity_preserving_outcome"]) for row in values),
                "safe_stop": mean(as_bool(row["safe_stop"]) for row in values),
                "repair_trigger": mean(as_bool(row["repair_trigger"]) for row in values),
                "conditional_repair_success": (
                    mean(as_bool(row["repair_success"]) for row in failed) if failed else 0.0
                ),
                "residue_cases_recovered": sum(not as_bool(row["final_residue"]) for row in residue_cases),
                "residue_case_count": len(residue_cases),
                "unnecessary_repair": mean(as_bool(row["unnecessary_repair"]) for row in values),
                "repair_induced_side_effect": mean(as_bool(row["repair_induced_side_effect"]) for row in values),
                "mean_token_cost": mean(float(row["token_cost"]) for row in values),
                "mean_call_count": mean(float(row["call_count"]) for row in values),
            }
        )
    write_csv(AGGREGATE, aggregate_rows)

    expected_metrics = {
        "C-SDVR-LLMRepair": (236, 0, 240, 4, 17),
        "C-SDVR-OracleUpperBound": (240, 0, 240, 0, 21),
        "FinalReplay": (227, 4, 227, 0, 8),
        "JudgeRepair": (216, 13, 216, 0, 17),
        "NoCheck": (219, 9, 219, 0, 0),
    }
    for policy, (successes, residues, integrity, safe_stops, repairs) in expected_metrics.items():
        values = [row for row in rows if row["policy"] == policy]
        observed = (
            sum(as_bool(row["final_success"]) for row in values),
            sum(as_bool(row["final_residue"]) for row in values),
            sum(as_bool(row["integrity_preserving_outcome"]) for row in values),
            sum(as_bool(row["safe_stop"]) for row in values),
            sum(as_bool(row["repair_success"]) for row in values),
        )
        check(f"aggregate counts: {policy}", observed == (successes, residues, integrity, safe_stops, repairs), f"observed={observed}")

    published_summary = read_csv(AUTONOMOUS_SUMMARY)
    check("model-policy summary rows", len(published_summary) == 10, f"observed={len(published_summary)}")
    for summary_row in published_summary:
        values = [
            row for row in rows
            if row["model"] == summary_row["model"] and row["policy"] == summary_row["policy"]
        ]
        recomputed_success = mean(as_bool(row["final_success"]) for row in values)
        recomputed_residue = mean(as_bool(row["final_residue"]) for row in values)
        check(
            f"summary success/residue: {summary_row['model']} {summary_row['policy']}",
            abs(recomputed_success - float(summary_row["final_success"])) < 1e-12
            and abs(recomputed_residue - float(summary_row["final_residue"])) < 1e-12,
            f"recomputed=({recomputed_success:.12f},{recomputed_residue:.12f})",
        )

    scale_rows = read_csv(SCALE_RAW)
    check("scalability row count", len(scale_rows) == 192, f"observed={len(scale_rows)}, expected=192")
    check(
        "scalability design cells",
        len({(row["repository_files"], row["file_size_bytes"], row["mutation_width"]) for row in scale_rows}) == 24,
        "4 repository sizes x 2 file sizes x 3 mutation widths",
    )
    check(
        "scalability repeats",
        all(count == 8 for count in Counter((row["repository_files"], row["file_size_bytes"], row["mutation_width"]) for row in scale_rows).values()),
        "eight repeats per design cell",
    )
    check(
        "scalability verification integrity",
        all(as_bool(row["verification_correct"]) and as_bool(row["rollback_success"]) for row in scale_rows),
        "all exact-diff and clean-Git rollback assertions passed",
    )

    contrast_rows = read_csv(PAIRED_CONTRASTS)
    check("paired contrast row count", len(contrast_rows) == 16, f"observed={len(contrast_rows)}, expected=16")
    check(
        "paired contrast design",
        all(
            int(row["task_clusters"]) == 40
            and int(row["paired_trajectories"]) == 240
            and int(row["bootstrap_resamples"]) == 10_000
            for row in contrast_rows
        ),
        "40 task clusters, 240 paired trajectories, and 10,000 resamples per contrast",
    )
    expected_contrasts = {
        ("NoCheck", "final_success"): 0.07083333333333333,
        ("NoCheck", "final_residue"): 0.0375,
        ("NoCheck", "integrity_preserving_outcome"): 0.0875,
        ("NoCheck", "token_cost"): -81.03333333333333,
        ("FinalReplay", "final_success"): 0.0375,
        ("FinalReplay", "final_residue"): 0.016666666666666666,
        ("FinalReplay", "integrity_preserving_outcome"): 0.05416666666666667,
        ("FinalReplay", "token_cost"): -16.308333333333334,
        ("JudgeRepair", "final_success"): 0.08333333333333333,
        ("JudgeRepair", "final_residue"): 0.05416666666666667,
        ("JudgeRepair", "integrity_preserving_outcome"): 0.1,
        ("JudgeRepair", "token_cost"): 674.1083333333333,
        ("C-SDVR-OracleUpperBound", "final_success"): -0.016666666666666666,
        ("C-SDVR-OracleUpperBound", "final_residue"): 0.0,
        ("C-SDVR-OracleUpperBound", "integrity_preserving_outcome"): 0.0,
        ("C-SDVR-OracleUpperBound", "token_cost"): -81.03333333333333,
    }
    observed_contrasts = {
        (row["baseline_policy"], row["metric"]): float(row["estimate"])
        for row in contrast_rows
    }
    for key, expected in expected_contrasts.items():
        observed = observed_contrasts.get(key)
        observed_text = "missing" if observed is None else f"{observed:.12f}"
        check(
            f"paired contrast estimate: {key[0]} {key[1]}",
            observed is not None and abs(observed - expected) < 1e-12,
            f"observed={observed_text}, expected={expected:.12f}",
        )

    failures = [item for item in checks if not item[1]]
    lines = [
        "# ASE Revision Numeric Audit v6",
        "",
        f"Checks: {len(checks)}",
        f"Failures: {len(failures)}",
        "",
        "## Aggregate autonomous-repair metrics",
        "",
        "| Policy | N | Final success | Final residue | Integrity outcome | Safe stop | Conditional repair success | Residue recovered | Mean tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in aggregate_rows:
        lines.append(
            f"| {row['policy']} | {row['policy_rows']} | {row['final_success']:.3f} | {row['final_residue']:.3f} | "
            f"{row['integrity_preserving_outcome']:.3f} | {row['safe_stop']:.3f} | "
            f"{row['conditional_repair_success']:.3f} | {row['residue_cases_recovered']}/{row['residue_case_count']} | "
            f"{row['mean_token_cost']:.1f} |"
        )
    lines.extend(["", "## Checks", ""])
    for name, passed, detail in checks:
        lines.append(f"- {'PASS' if passed else 'FAIL'}: {name} ({detail})")
    AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(AUDIT)
    print(f"ase_revision_checks={len(checks)}")
    print(f"ase_revision_failures={len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
