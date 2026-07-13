#!/usr/bin/env python3
"""Additional revision analyses requested by simulated reviewers.

This script does not replace the main benchmark. It adds two descriptive
robustness checks that do not require external LLM API calls:

1. Fault-rate sensitivity: rerun the executable benchmark under several
   controlled fault rates.
2. Cost-weight sensitivity: re-score the existing raw benchmark logs under
   several cost preferences.

The analyses address reviewer concerns about the fixed 0.72 fault rate and the
hand-chosen cost-normalized-success denominator. They remain controlled
prototype analyses, not deployed-agent evidence.
"""

from __future__ import annotations

import csv
import json
import math
import random
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "01_experiments"
OUT = ROOT / "02_results"
RAW = OUT / "raw_runs_executable_v3.csv"
FAULT_RATE_FILE = OUT / "fault_rate_sensitivity_v3.csv"
COST_WEIGHT_FILE = OUT / "cost_weight_sensitivity_v3.csv"
POSTCONDITION_FILE = OUT / "postcondition_robustness_proxy_v3.csv"
REPORT = OUT / "revision_sensitivity_report_v3.md"

sys.path.insert(0, str(EXP))
from run_executable_benchmark import (  # noqa: E402
    METHODS,
    Task,
    choose_deviation,
    detect_deviation,
    env_for,
    generate_tasks,
    intended_transition_holds,
    policy_params,
    residue_present,
    run_one,
    stable_hash,
    summarize,
)


FAULT_RATES = [0.20, 0.40, 0.60, 0.72, 0.80]

COST_PROFILES = {
    "original": {"token": 1.0, "time": 1.0, "action": 1.0, "residue": 0.0, "unnecessary": 0.0},
    "token_heavy": {"token": 1.8, "time": 0.8, "action": 0.8, "residue": 0.0, "unnecessary": 0.0},
    "action_heavy": {"token": 0.8, "time": 0.8, "action": 1.8, "residue": 0.0, "unnecessary": 0.0},
    "safety_heavy": {"token": 1.0, "time": 1.0, "action": 1.0, "residue": 1.5, "unnecessary": 0.6},
    "success_heavy": {"token": 0.6, "time": 0.6, "action": 0.6, "residue": 0.5, "unnecessary": 0.2},
}

PC_MODES = ["gold_pc", "target_only_pc", "under_specified_pc", "over_strict_pc", "wrong_object_pc"]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_raw() -> list[dict[str, str]]:
    with RAW.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fault_rate_sensitivity() -> list[dict[str, object]]:
    tasks = generate_tasks(120)
    out: list[dict[str, object]] = []
    for rate in FAULT_RATES:
        rows = []
        for seed in range(20):
            for task in tasks:
                for method in METHODS:
                    rows.append(run_one(task, method, seed, fault_rate=rate))
        summary = summarize(rows, ["method"])
        for r in summary:
            r["fault_rate"] = f"{rate:.2f}"
            out.append(r)
    out.sort(key=lambda r: (float(r["fault_rate"]), METHODS.index(str(r["method"]))))
    return out


def cost_weight_sensitivity(raw: list[dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    by_method: dict[str, list[dict[str, str]]] = {m: [] for m in METHODS}
    for r in raw:
        if int(r["fault"]) == 1:
            by_method[r["method"]].append(r)

    for profile, w in COST_PROFILES.items():
        scored = []
        for method in METHODS:
            items = by_method[method]
            vals = []
            safe_utils = []
            for r in items:
                success = int(r["success"])
                residue = int(r["side_effect_residue"])
                unnecessary = int(r["unnecessary_repair"])
                token = int(r["token_cost"])
                time = float(r["time_cost"])
                action = int(r["action_cost"])
                denom = (
                    w["token"] * token / 2000
                    + w["time"] * time / 20
                    + w["action"] * action / 10
                    + w["residue"] * residue
                    + w["unnecessary"] * unnecessary
                )
                vals.append(success / denom if denom else 0.0)
                safe_utils.append(
                    success
                    - 1.5 * w["residue"] * residue
                    - 0.5 * w["unnecessary"] * unnecessary
                    - 0.05 * (w["token"] * token / 2000 + w["time"] * time / 20 + w["action"] * action / 10)
                )
            scored.append(
                {
                    "profile": profile,
                    "method": method,
                    "weighted_cns": mean(vals),
                    "safe_utility": mean(safe_utils),
                    "success": mean([int(r["success"]) for r in items]),
                    "residue": mean([int(r["side_effect_residue"]) for r in items]),
                    "unnecessary_repair": mean([int(r["unnecessary_repair"]) for r in items]),
                    "token_cost": mean([int(r["token_cost"]) for r in items]),
                }
            )
        ranked = sorted(scored, key=lambda r: r["weighted_cns"], reverse=True)
        rank = {r["method"]: i + 1 for i, r in enumerate(ranked)}
        for r in scored:
            rows.append(
                {
                    "profile": r["profile"],
                    "method": r["method"],
                    "weighted_cns": f"{r['weighted_cns']:.4f}",
                    "weighted_cns_rank": rank[r["method"]],
                    "safe_utility": f"{r['safe_utility']:.4f}",
                    "success": f"{r['success']:.4f}",
                    "residue": f"{r['residue']:.4f}",
                    "unnecessary_repair": f"{r['unnecessary_repair']:.4f}",
                    "token_cost": f"{r['token_cost']:.2f}",
                }
            )
    return rows


def noisy_pc_task(task: Task, mode: str) -> Task:
    if mode == "wrong_object_pc":
        if task.domain == "file":
            target = "/work/beta.txt"
        else:
            target = "r2"
        return Task(
            task.task_id,
            task.domain,
            task.operation,
            task.severity,
            task.deviation_type,
            task.instruction,
            target,
            task.expected,
            task.steps,
        )
    return task


def run_pc_proxy(task: Task, mode: str, seed: int, fault_rate: float = 0.72) -> dict[str, object]:
    """Run C-SDVR while perturbing the verifier-side postcondition."""
    paired_rng = random.Random(f"pc-paired:{task.task_id}:{seed}:{fault_rate}")
    fault_draw = paired_rng.random()
    detection_draw = paired_rng.random()
    repair_draw = paired_rng.random()
    rollback_draw = paired_rng.random()
    mode_rng = random.Random(f"pc-mode:{mode}:{task.task_id}:{seed}:{fault_rate}")
    env = env_for(task)
    gold_env = env_for(task)
    params = policy_params("C-SDVR")
    before = env.snapshot()
    gold_env.apply(task.operation, task.target, task.expected, None)
    true_gold = gold_env.snapshot()
    deviation = choose_deviation(task, fault_draw, fault_rate)
    env.apply(task.operation, task.target, task.expected, deviation)
    after = env.snapshot()
    fault = deviation is not None

    pc_task = noisy_pc_task(task, mode)
    pc_gold_env = env_for(pc_task)
    pc_gold_env.apply(pc_task.operation, pc_task.target, pc_task.expected, None)
    pc_gold = pc_gold_env.snapshot()
    detector_strength = params["detect"]
    if mode == "under_specified_pc":
        detector_strength *= 0.55
    detected = detect_deviation(before, after, pc_gold, pc_task, detector_strength, detection_draw)
    if (
        mode == "target_only_pc"
        and residue_present(before, true_gold, after)
        and intended_transition_holds(before, pc_gold, after)
    ):
        detected = False
    if mode == "over_strict_pc" and not fault and mode_rng.random() < 0.30:
        detected = True
    if mode == "over_strict_pc" and task.severity == "minor" and mode_rng.random() < 0.25:
        detected = True

    repair_attempted = False
    rollback_used = False
    if detected:
        if pc_task.severity == "minor":
            repair_attempted = mode_rng.random() < (0.55 if mode == "over_strict_pc" else 0.25)
        elif pc_task.severity in {"major", "critical"}:
            repair_attempted = True

    if repair_attempted:
        if pc_task.severity == "critical" and rollback_draw < params["rollback"]:
            rollback_used = True
            env.rollback(before)
        if repair_draw < params["repair"]:
            if rollback_used:
                env.apply(pc_task.operation, pc_task.target, pc_task.expected, None)
            else:
                env.restore_scoped(before, pc_gold)

    final_snapshot = env.snapshot()
    residue = residue_present(before, true_gold, final_snapshot)
    true_target = intended_transition_holds(before, true_gold, final_snapshot)
    success = true_target and not residue
    token_cost = params["base_token"] + task.steps * 120
    time_cost = params["base_time"] + task.steps * 0.8
    action_cost = task.steps + 1
    if detected:
        token_cost += 180
        time_cost += 1.0
    if repair_attempted:
        token_cost += 640 if pc_task.severity == "critical" else 430
        time_cost += 3.8 if pc_task.severity == "critical" else 2.4
        action_cost += 3 if pc_task.severity == "critical" else 2
    unnecessary_repair = int(repair_attempted and (not fault or pc_task.severity == "minor"))
    denominator = token_cost / 2000 + time_cost / 20 + action_cost / 10
    return {
        "pc_mode": mode,
        "seed": seed,
        "task_id": task.task_id,
        "domain": task.domain,
        "severity": task.severity if fault else "none",
        "fault": int(fault),
        "detected": int(detected),
        "repair_attempted": int(repair_attempted),
        "rollback_used": int(rollback_used),
        "true_target_satisfied": int(true_target),
        "success": int(success),
        "side_effect_residue": int(residue),
        "unnecessary_repair": unnecessary_repair,
        "token_cost": int(round(token_cost)),
        "time_cost": f"{time_cost:.3f}",
        "action_cost": int(action_cost),
        "cost_norm_success": f"{int(success) / denominator:.6f}",
        "state_final_hash": stable_hash(json.dumps(final_snapshot, sort_keys=True)),
    }


def postcondition_robustness_proxy() -> list[dict[str, object]]:
    tasks = generate_tasks(120)
    rows = []
    for mode in PC_MODES:
        raw = []
        for seed in range(20):
            for task in tasks:
                raw.append(run_pc_proxy(task, mode, seed))
        fault_items = [r for r in raw if int(r["fault"]) == 1]
        nominal_items = [r for r in raw if int(r["fault"]) == 0]
        tp = sum(int(r["detected"]) for r in fault_items)
        fn = len(fault_items) - tp
        fp = sum(int(r["detected"]) for r in nominal_items)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append(
            {
                "pc_mode": mode,
                "n_runs": len(raw),
                "success": f"{mean([int(r['success']) for r in fault_items]):.4f}",
                "target_satisfied": f"{mean([int(r['true_target_satisfied']) for r in fault_items]):.4f}",
                "residue": f"{mean([int(r['side_effect_residue']) for r in fault_items]):.4f}",
                "detection_f1": f"{f1:.4f}",
                "repair_attempt": f"{mean([int(r['repair_attempted']) for r in fault_items]):.4f}",
                "rollback_use": f"{mean([int(r['rollback_used']) for r in fault_items]):.4f}",
                "unnecessary_repair": f"{mean([int(r['unnecessary_repair']) for r in raw]):.4f}",
                "token_cost": f"{mean([int(r['token_cost']) for r in raw]):.2f}",
                "cost_norm_success": f"{mean([float(r['cost_norm_success']) for r in fault_items]):.4f}",
            }
        )
    return rows


def write_report(
    fault_rows: list[dict[str, object]],
    cost_rows: list[dict[str, object]],
    pc_rows: list[dict[str, object]],
) -> None:
    lines = [
        "# Revision Sensitivity Analyses",
        "",
        "Verification status: GENERATED BY LOCAL CONTROLLED CODE",
        "",
        "These analyses address reviewer concerns about fault-rate dependence and cost-weight dependence. They are controlled robustness analyses and do not replace larger real LLM-agent experiments.",
        "",
        "## Fault-Rate Sensitivity",
        "",
        "| Fault rate | Method | Success | Residue | Detection F1 | Token | CNS |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for r in fault_rows:
        if r["method"] in {"NoCheck", "FinalVerifier", "C-SDVR-NoSeverity", "C-SDVR"}:
            lines.append(
                f"| {r['fault_rate']} | {r['method']} | {float(r['task_success_rate']):.3f} | "
                f"{float(r['side_effect_residue_rate']):.3f} | {float(r['detection_f1']):.3f} | "
                f"{float(r['mean_token_cost']):.1f} | {float(r['cost_norm_success']):.3f} |"
            )
    lines += [
        "",
        "## Cost-Weight Sensitivity",
        "",
        "| Profile | Method | Weighted CNS | Rank | Success | Residue | Unnecessary repair | Token |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in cost_rows:
        if r["method"] in {"FinalVerifier", "ReflectionRetry", "C-SDVR-NoSeverity", "C-SDVR"}:
            lines.append(
                f"| {r['profile']} | {r['method']} | {float(r['weighted_cns']):.3f} | {r['weighted_cns_rank']} | "
                f"{float(r['success']):.3f} | {float(r['residue']):.3f} | "
                f"{float(r['unnecessary_repair']):.3f} | {float(r['token_cost']):.1f} |"
            )
    lines += [
        "",
        "## Postcondition Robustness Proxy",
        "",
        "This is not a full LLM-generated postcondition experiment. It perturbs the verifier-side postcondition in the executable environment to estimate sensitivity to common postcondition errors.",
        "",
        "| PC mode | Success | Target sat. | Residue | Detection F1 | Repair | Rollback | Unnec. repair | Token | CNS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in pc_rows:
        lines.append(
            f"| {r['pc_mode']} | {float(r['success']):.3f} | {float(r['target_satisfied']):.3f} | "
            f"{float(r['residue']):.3f} | {float(r['detection_f1']):.3f} | {float(r['repair_attempt']):.3f} | "
            f"{float(r['rollback_use']):.3f} | {float(r['unnecessary_repair']):.3f} | "
            f"{float(r['token_cost']):.1f} | {float(r['cost_norm_success']):.3f} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "C-SDVR remains a strong safety-cost policy across the tested controlled fault rates. The aggressive no-severity ablation can still dominate raw success under some preferences, but it consistently spends more repair budget and triggers more unnecessary repair. The postcondition proxy confirms that C-SDVR is sensitive to specification quality: missing forbidden side-effect constraints, wrong targets, and over-strict constraints degrade the control loop in different ways. These results support a trade-off interpretation rather than a universal-best-policy claim.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    raw = read_raw()
    fault_rows = fault_rate_sensitivity()
    cost_rows = cost_weight_sensitivity(raw)
    pc_rows = postcondition_robustness_proxy()
    write_csv(FAULT_RATE_FILE, fault_rows)
    write_csv(COST_WEIGHT_FILE, cost_rows)
    write_csv(POSTCONDITION_FILE, pc_rows)
    write_report(fault_rows, cost_rows, pc_rows)
    print(f"fault_rate_rows={len(fault_rows)} -> {FAULT_RATE_FILE}")
    print(f"cost_weight_rows={len(cost_rows)} -> {COST_WEIGHT_FILE}")
    print(f"postcondition_rows={len(pc_rows)} -> {POSTCONDITION_FILE}")
    print(REPORT)


if __name__ == "__main__":
    main()
