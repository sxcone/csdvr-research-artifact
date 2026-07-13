#!/usr/bin/env python3
"""Cost-tradeoff and Pareto analysis for C-SDVR v4 revision."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt


plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 10,
        "axes.labelsize": 10,
        "axes.titlesize": 11,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
    }
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "02_results"
FIGS = RESULTS / "figures"
MAIN = RESULTS / "summary_metrics_executable_v3.csv"
COST = RESULTS / "cost_weight_sensitivity_v3.csv"
OUT = RESULTS / "cost_tradeoff_pareto_v4.csv"
FIG_PDF = FIGS / "cost_tradeoff_pareto_v4.pdf"
FIG_PNG = FIGS / "cost_tradeoff_pareto_v4.png"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def is_dominated(row: dict[str, float], rows: list[dict[str, float]]) -> bool:
    for other in rows:
        if other is row:
            continue
        no_worse = (
            other["success"] >= row["success"]
            and other["token_cost"] <= row["token_cost"]
            and other["residue"] <= row["residue"]
            and other["unnecessary_repair"] <= row["unnecessary_repair"]
        )
        strictly_better = (
            other["success"] > row["success"]
            or other["token_cost"] < row["token_cost"]
            or other["residue"] < row["residue"]
            or other["unnecessary_repair"] < row["unnecessary_repair"]
        )
        if no_worse and strictly_better:
            return True
    return False


def main() -> None:
    rows = []
    for r in read_csv(MAIN):
        rows.append(
            {
                "method": r["method"],
                "success": float(r["task_success_rate"]),
                "residue": float(r["side_effect_residue_rate"]),
                "unnecessary_repair": float(r["unnecessary_repair_rate"]),
                "token_cost": float(r["mean_token_cost"]),
                "cost_norm_success": float(r["cost_norm_success"]),
            }
        )
    for r in rows:
        r["pareto_frontier"] = not is_dominated(r, rows)
        r["residue_constrained"] = r["residue"] <= 0.30
        r["low_unnecessary_repair"] = r["unnecessary_repair"] <= 0.05

    cost_rows = read_csv(COST)
    profiles = sorted({r["profile"] for r in cost_rows})
    by_method = {r["method"]: r for r in rows}
    for method in by_method:
        ranks = [int(float(r["weighted_cns_rank"])) for r in cost_rows if r["method"] == method]
        by_method[method]["best_weighted_rank"] = min(ranks) if ranks else ""
        by_method[method]["worst_weighted_rank"] = max(ranks) if ranks else ""
        by_method[method]["tested_cost_profiles"] = len(ranks)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        fields = [
            "method",
            "success",
            "residue",
            "unnecessary_repair",
            "token_cost",
            "cost_norm_success",
            "pareto_frontier",
            "residue_constrained",
            "low_unnecessary_repair",
            "best_weighted_rank",
            "worst_weighted_rank",
            "tested_cost_profiles",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    FIGS.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(7.2, 4.2))
    label_offsets = {
        "NoCheck": (20, 0.010),
        "FinalVerifier": (35, 0.022),
        "StepVerifier": (20, -0.018),
        "ReflectionRetry": (20, 0.008),
        "C-SDVR-NoRollback": (-200, -0.028),
        "C-SDVR-NoSeverity": (20, -0.014),
        "C-SDVR": (20, 0.008),
    }
    display_names = {
        "ReflectionRetry": "Reflection retry",
        "C-SDVR-NoRollback": "No rollback",
        "C-SDVR-NoSeverity": "No severity",
    }
    for r in rows:
        size = 80 + 1200 * r["residue"]
        marker = "D" if r["pareto_frontier"] else "o"
        color = "#1b9e77" if r["method"] == "C-SDVR" else "#7570b3" if r["method"] == "C-SDVR-NoSeverity" else "#666666"
        plt.scatter(r["token_cost"], r["success"], s=size, marker=marker, color=color, alpha=0.82, edgecolor="white", linewidth=0.8)
        dx, dy = label_offsets[r["method"]]
        plt.text(
            r["token_cost"] + dx,
            r["success"] + dy,
            display_names.get(r["method"], r["method"]),
            fontsize=9,
        )
    plt.xlabel("Mean token-cost proxy")
    plt.ylabel("Task success")
    plt.title("Success-cost Pareto view; marker size encodes residual side effects")
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(FIG_PDF)
    plt.savefig(FIG_PNG, dpi=250)
    print(OUT)
    print(FIG_PDF)
    print(FIG_PNG)


if __name__ == "__main__":
    main()
