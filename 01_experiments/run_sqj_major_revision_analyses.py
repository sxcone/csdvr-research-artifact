#!/usr/bin/env python3
"""Reviewer-requested denominator, capability, class, and measured-cost analyses."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib.pyplot as plt

from run_executable_benchmark import generate_tasks, run_one


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "02_results"
FIGURES = RESULTS / "figures"

MAIN_RAW = RESULTS / "raw_runs_executable_v3.csv"
LIVE_RAW = RESULTS / "live_validation_raw_v3.csv"
BROWSER_RAW = RESULTS / "browser_validation_raw_v3.csv"

DENOMINATOR_OUT = RESULTS / "all_run_fault_conditioned_metrics_v5.csv"
CLASS_OUT = RESULTS / "deviation_class_outcomes_v5.csv"
GRID_OUT = RESULTS / "capability_grid_summary_v5.csv"
GRID_CLASS_OUT = RESULTS / "capability_grid_by_deviation_v5.csv"
CALIBRATION_OUT = RESULTS / "capability_calibration_v5.csv"
COST_OUT = RESULTS / "measured_execution_costs_v5.csv"
REPORT_OUT = RESULTS / "sqj_major_revision_analyses_v5.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def avg(rows: list[dict[str, Any]], field: str) -> float:
    return mean(float(row[field]) for row in rows) if rows else 0.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))
    return values[index]


def denominator_metrics(main_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in main_rows:
        groups[row["method"]].append(row)

    out: list[dict[str, Any]] = []
    for method, rows in sorted(groups.items()):
        fault = [row for row in rows if int(row["fault"]) == 1]
        nominal = [row for row in rows if int(row["fault"]) == 0]
        fault_token = avg(fault, "token_cost")
        nominal_token = avg(nominal, "token_cost")
        out.append(
            {
                "method": method,
                "n_all": len(rows),
                "n_fault": len(fault),
                "fault_prevalence": f"{len(fault) / len(rows):.4f}",
                "all_run_success": f"{avg(rows, 'success'):.4f}",
                "fault_conditioned_success": f"{avg(fault, 'success'):.4f}",
                "nominal_success": f"{avg(nominal, 'success'):.4f}",
                "all_run_residue": f"{avg(rows, 'side_effect_residue'):.4f}",
                "fault_conditioned_residue": f"{avg(fault, 'side_effect_residue'):.4f}",
                "nominal_residue": f"{avg(nominal, 'side_effect_residue'):.4f}",
                "all_run_token_cost": f"{avg(rows, 'token_cost'):.2f}",
                "fault_only_token_cost": f"{fault_token:.2f}",
                "nominal_token_cost": f"{nominal_token:.2f}",
                "fault_recovery_token_increment": f"{fault_token - nominal_token:.2f}",
                "all_run_time_proxy": f"{avg(rows, 'time_cost'):.3f}",
                "fault_only_time_proxy": f"{avg(fault, 'time_cost'):.3f}",
                "nominal_time_proxy": f"{avg(nominal, 'time_cost'):.3f}",
            }
        )
    return out


def deviation_class_metrics(
    main_rows: list[dict[str, str]],
    live_rows: list[dict[str, str]],
    browser_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in main_rows:
        if int(row["fault"]) != 1:
            continue
        normalized.append(
            {
                "environment": "controlled",
                "domain": row["domain"],
                "method": row["method"],
                "deviation_class": row["deviation_type"],
                "success": row["success"],
                "residue": row["side_effect_residue"],
                "detected": row["detected"],
                "repair_attempted": row["repair_attempted"],
                "rollback_used": row["rollback_used"],
                "token_cost": row["token_cost"],
            }
        )
    for environment, rows in (("live", live_rows), ("browser", browser_rows)):
        for row in rows:
            if row["fault"] == "none":
                continue
            normalized.append(
                {
                    "environment": environment,
                    "domain": row["domain"],
                    "method": row["method"],
                    "deviation_class": row["fault"],
                    "success": row["success"],
                    "residue": row["residue"],
                    "detected": row["detected"],
                    "repair_attempted": row["repair_attempted"],
                    "rollback_used": row["rollback_used"],
                    "token_cost": row["token_cost"],
                }
            )

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        groups[(row["environment"], row["domain"], row["method"], row["deviation_class"])].append(row)

    out: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items()):
        out.append(
            {
                "environment": key[0],
                "domain": key[1],
                "method": key[2],
                "deviation_class": key[3],
                "n_fault": len(rows),
                "success": f"{avg(rows, 'success'):.4f}",
                "residue": f"{avg(rows, 'residue'):.4f}",
                "detection_recall": f"{avg(rows, 'detected'):.4f}",
                "repair_attempt_rate": f"{avg(rows, 'repair_attempted'):.4f}",
                "rollback_use_rate": f"{avg(rows, 'rollback_used'):.4f}",
                "mean_token_cost": f"{avg(rows, 'token_cost'):.2f}",
            }
        )
    return out


def capability_grid() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detector_values = [0.60, 0.75, 0.90, 1.00]
    repair_values = [0.50, 0.65, 0.78, 0.90]
    rollback_values = [0.60, 0.75, 0.92, 1.00]
    tasks = generate_tasks(120)
    summary: list[dict[str, Any]] = []
    by_class: list[dict[str, Any]] = []

    for rollback in rollback_values:
        for detector in detector_values:
            for repair in repair_values:
                capabilities = {"detect": detector, "repair": repair, "rollback": rollback}
                rows = [
                    run_one(task, "C-SDVR", seed, capabilities=capabilities)
                    for seed in range(5)
                    for task in tasks
                ]
                fault = [row for row in rows if int(row["fault"]) == 1]
                rollback_attempts = [row for row in fault if int(row["rollback_attempted"]) == 1]
                summary.append(
                    {
                        "detector": f"{detector:.2f}",
                        "repair": f"{repair:.2f}",
                        "rollback": f"{rollback:.2f}",
                        "n_all": len(rows),
                        "n_fault": len(fault),
                        "fault_prevalence": f"{len(fault) / len(rows):.4f}",
                        "fault_success": f"{avg(fault, 'success'):.4f}",
                        "fault_residue": f"{avg(fault, 'side_effect_residue'):.4f}",
                        "detection_recall": f"{avg(fault, 'detected'):.4f}",
                        "repair_operation_success": f"{avg([r for r in fault if int(r['repair_attempted'])], 'repair_operation_succeeded'):.4f}",
                        "rollback_success": f"{avg(rollback_attempts, 'rollback_used'):.4f}",
                        "mean_token_cost_all": f"{avg(rows, 'token_cost'):.2f}",
                        "mean_token_cost_fault": f"{avg(fault, 'token_cost'):.2f}",
                    }
                )
                class_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for row in fault:
                    class_groups[str(row["deviation_type"])].append(row)
                for deviation, items in sorted(class_groups.items()):
                    by_class.append(
                        {
                            "detector": f"{detector:.2f}",
                            "repair": f"{repair:.2f}",
                            "rollback": f"{rollback:.2f}",
                            "deviation_class": deviation,
                            "n_fault": len(items),
                            "success": f"{avg(items, 'success'):.4f}",
                            "residue": f"{avg(items, 'side_effect_residue'):.4f}",
                            "detection_recall": f"{avg(items, 'detected'):.4f}",
                        }
                    )
    return summary, by_class


def calibration_metrics(live_rows: list[dict[str, str]], browser_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {
            "source": "controlled_design_point",
            "domain": "pooled",
            "method": "C-SDVR",
            "detector_recall": "0.9000",
            "repair_success_given_attempt": "0.7800",
            "rollback_success_given_attempt": "0.9200",
            "interpretation": "pre-registered imperfect-component design point; not fitted to deployment data",
        }
    ]
    for source, rows in (("live_closed_scope", live_rows), ("browser_closed_scope", browser_rows)):
        domains = sorted({row["domain"] for row in rows})
        for domain in domains:
            items = [row for row in rows if row["method"] == "C-SDVR" and row["domain"] == domain and row["fault"] != "none"]
            repairs = [row for row in items if int(row["repair_attempted"]) == 1]
            rollbacks = [row for row in items if int(row["rollback_used"]) == 1]
            out.append(
                {
                    "source": source,
                    "domain": domain,
                    "method": "C-SDVR",
                    "detector_recall": f"{avg(items, 'detected'):.4f}",
                    "repair_success_given_attempt": f"{avg(repairs, 'success'):.4f}",
                    "rollback_success_given_attempt": f"{avg(rollbacks, 'success'):.4f}",
                    "interpretation": "oracle-like scripted recovery under complete local scope; upper-bound diagnostic",
                }
            )
    return out


def measured_costs(live_rows: list[dict[str, str]], browser_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for source, rows in (("live", live_rows), ("browser", browser_rows)):
        for row in rows:
            groups[(source, row["domain"], row["method"])].append(row)
    out: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items()):
        fault = [row for row in rows if row["fault"] != "none"]
        rollback = [row for row in rows if int(row["rollback_used"]) == 1]
        wall = [float(row["wall_clock_ms"]) for row in rows]
        out.append(
            {
                "environment": key[0],
                "domain": key[1],
                "method": key[2],
                "n_all": len(rows),
                "n_fault": len(fault),
                "mean_wall_clock_ms_all": f"{mean(wall):.3f}",
                "p50_wall_clock_ms_all": f"{percentile(wall, 0.50):.3f}",
                "p95_wall_clock_ms_all": f"{percentile(wall, 0.95):.3f}",
                "mean_wall_clock_ms_fault": f"{avg(fault, 'wall_clock_ms'):.3f}",
                "mean_snapshot_bytes": f"{avg(rows, 'snapshot_bytes'):.2f}",
                "mean_rollback_bytes_when_used": f"{avg(rollback, 'rollback_bytes'):.2f}",
                "mean_token_proxy_all": f"{avg(rows, 'token_cost'):.2f}",
                "mean_time_proxy_all": f"{avg(rows, 'time_cost'):.3f}",
            }
        )
    return out


def plot_grid(rows: list[dict[str, Any]]) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    detector_values = sorted({float(row["detector"]) for row in rows})
    repair_values = sorted({float(row["repair"]) for row in rows})
    rollback_values = sorted({float(row["rollback"]) for row in rows})
    lookup = {
        (float(row["detector"]), float(row["repair"]), float(row["rollback"])): float(row["fault_success"])
        for row in rows
    }
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.2), constrained_layout=True)
    image = None
    for ax, rollback in zip(axes.flat, rollback_values):
        matrix = [[lookup[(detector, repair, rollback)] for repair in repair_values] for detector in detector_values]
        image = ax.imshow(matrix, vmin=0, vmax=1, cmap="viridis", aspect="auto")
        ax.set_title(f"Rollback capability = {rollback:.2f}")
        ax.set_xticks(range(len(repair_values)), [f"{value:.2f}" for value in repair_values])
        ax.set_yticks(range(len(detector_values)), [f"{value:.2f}" for value in detector_values])
        ax.set_xlabel("Repair capability")
        ax.set_ylabel("Detector capability")
        for i, detector in enumerate(detector_values):
            for j, repair in enumerate(repair_values):
                value = lookup[(detector, repair, rollback)]
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="white" if value < 0.58 else "black", fontsize=8)
    if image is not None:
        fig.colorbar(image, ax=axes, label="Fault-conditioned success", shrink=0.86)
    fig.suptitle("Independent detector, repair, and rollback sensitivity")
    fig.savefig(FIGURES / "capability_grid_v5.pdf", bbox_inches="tight")
    fig.savefig(FIGURES / "capability_grid_v5.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def write_report(
    denominator: list[dict[str, Any]],
    grid: list[dict[str, Any]],
    calibration: list[dict[str, Any]],
    costs: list[dict[str, Any]],
) -> None:
    baseline = next(row for row in grid if row["detector"] == "0.90" and row["repair"] == "0.78" and row["rollback"] == "0.92")
    csdvr = next(row for row in denominator if row["method"] == "C-SDVR")
    lines = [
        "# SQJ Major-Revision Quantitative Analyses",
        "",
        "## Denominator Transparency",
        "",
        f"The main controlled benchmark has fault prevalence {csdvr['fault_prevalence']}. C-SDVR all-run success is {csdvr['all_run_success']}; fault-conditioned recovery success is {csdvr['fault_conditioned_success']}. Mean all-run and fault-only token proxies are {csdvr['all_run_token_cost']} and {csdvr['fault_only_token_cost']}.",
        "",
        "## Capability Grid",
        "",
        f"The independent 4 x 4 x 4 grid contains {len(grid)} capability combinations. At detector=0.90, repair=0.78, and rollback=0.92, fault-conditioned success is {baseline['fault_success']} and residue is {baseline['fault_residue']}.",
        "",
        "The three values are design-point capabilities for studying controller structure. They are not estimates of deployed component accuracy. Closed-scope live/browser repair is oracle-like and is reported as an upper-bound diagnostic rather than calibration evidence.",
        "",
        "## Measured Costs",
        "",
        "Wall-clock time, serialized snapshot size, and changed rollback payload are measured directly for the local file/SQLite and Chromium/SQLite runs. Values remain machine- and implementation-specific and do not include external API billing or human confirmation.",
        "",
        "## Calibration Rows",
        "",
        "| Source | Domain | Detector | Repair | Rollback | Interpretation |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in calibration:
        lines.append(
            f"| {row['source']} | {row['domain']} | {row['detector_recall']} | {row['repair_success_given_attempt']} | "
            f"{row['rollback_success_given_attempt']} | {row['interpretation']} |"
        )
    lines += [
        "",
        "## Output Files",
        "",
        f"- `{DENOMINATOR_OUT.name}`",
        f"- `{CLASS_OUT.name}`",
        f"- `{GRID_OUT.name}`",
        f"- `{GRID_CLASS_OUT.name}`",
        f"- `{CALIBRATION_OUT.name}`",
        f"- `{COST_OUT.name}`",
        "- `figures/capability_grid_v5.pdf`",
        "",
    ]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    main_rows = read_csv(MAIN_RAW)
    live_rows = read_csv(LIVE_RAW)
    browser_rows = read_csv(BROWSER_RAW)

    denominator = denominator_metrics(main_rows)
    classes = deviation_class_metrics(main_rows, live_rows, browser_rows)
    grid, grid_classes = capability_grid()
    calibration = calibration_metrics(live_rows, browser_rows)
    costs = measured_costs(live_rows, browser_rows)

    write_csv(DENOMINATOR_OUT, denominator)
    write_csv(CLASS_OUT, classes)
    write_csv(GRID_OUT, grid)
    write_csv(GRID_CLASS_OUT, grid_classes)
    write_csv(CALIBRATION_OUT, calibration)
    write_csv(COST_OUT, costs)
    plot_grid(grid)
    write_report(denominator, grid, calibration, costs)

    print(f"denominator_rows={len(denominator)}")
    print(f"class_rows={len(classes)}")
    print(f"capability_grid_rows={len(grid)}")
    print(f"capability_class_rows={len(grid_classes)}")
    print(f"cost_rows={len(costs)}")


if __name__ == "__main__":
    main()
