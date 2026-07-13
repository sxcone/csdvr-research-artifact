#!/usr/bin/env python3
"""Bounded multi-step workflow validation for C-SDVR v4.

The workflow experiment is intentionally local and reversible. It evaluates how
side-effect residue accumulates across several file/form-like steps and whether
local rollback limits the recovery scope.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
RAW = OUT / "workflow_validation_raw_v4.csv"
SUMMARY = OUT / "workflow_validation_summary_v4.csv"
REPORT = OUT / "workflow_validation_report_v4.md"
ROLLBACK_DEPTH = OUT / "workflow_rollback_depth_v4.csv"
CASE_STUDY = OUT / "workflow_case_study_v4.md"

METHODS = ["NoCheck", "FinalVerifier", "ReflectionRetry", "C-SDVR"]
WORKFLOWS = ["student_records", "file_report"]
SEEDS = range(30)


def stable_hash(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


MISSING = ("__CSDVR_MISSING__",)


def semantic_state(state: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in state.items() if key != "audit"}


def flatten_state(value: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    if isinstance(value, dict):
        out: dict[tuple[str, ...], Any] = {}
        for key in sorted(value, key=str):
            out.update(flatten_state(value[key], prefix + (str(key),)))
        return out
    if isinstance(value, (list, tuple)):
        out = {}
        for index, item in enumerate(value):
            out.update(flatten_state(item, prefix + (str(index),)))
        return out
    return {prefix: value}


def transition_outcome(initial: dict[str, Any], gold: dict[str, Any], final: dict[str, Any]) -> tuple[bool, bool]:
    initial_flat = flatten_state(semantic_state(initial))
    gold_flat = flatten_state(semantic_state(gold))
    final_flat = flatten_state(semantic_state(final))
    intended_keys = {
        key
        for key in set(initial_flat) | set(gold_flat)
        if initial_flat.get(key, MISSING) != gold_flat.get(key, MISSING)
    }
    target_satisfied = bool(intended_keys) and all(
        final_flat.get(key, MISSING) == gold_flat.get(key, MISSING) for key in intended_keys
    )
    residue = any(
        final_flat.get(key, MISSING) != gold_flat.get(key, MISSING)
        and final_flat.get(key, MISSING) != initial_flat.get(key, MISSING)
        for key in set(initial_flat) | set(gold_flat) | set(final_flat)
    )
    return target_satisfied, residue


def changed_leaf_count(before: dict[str, Any], after: dict[str, Any]) -> int:
    before_flat = flatten_state(semantic_state(before))
    after_flat = flatten_state(semantic_state(after))
    return sum(
        before_flat.get(key, MISSING) != after_flat.get(key, MISSING)
        for key in set(before_flat) | set(after_flat)
    )


def initial_state(workflow: str) -> dict[str, Any]:
    if workflow == "student_records":
        return {
            "records": {
                "s001": {"name": "Alice", "grade": "B", "status": "active", "phone": "100"},
                "s002": {"name": "Bob", "grade": "C", "status": "active", "phone": "200"},
                "s999": {"name": "Temp", "grade": "F", "status": "pending", "phone": "999"},
            },
            "exports": {},
            "audit": [],
        }
    return {
        "files": {
            "inbox/draft.txt": "draft report",
            "inbox/data.csv": "metric,value\naccuracy,0.72\n",
            "archive/old.txt": "old",
            "backup/draft.txt": "draft report",
        },
        "reports": {},
        "audit": [],
    }


def workflow_steps(workflow: str) -> list[dict[str, Any]]:
    if workflow == "student_records":
        return [
            {"op": "create_student", "id": "s003", "value": {"name": "Carol", "grade": "A", "status": "active", "phone": "300"}},
            {"op": "edit_field", "id": "s001", "field": "phone", "value": "101"},
            {"op": "edit_field", "id": "s002", "field": "grade", "value": "B"},
            {"op": "delete_student", "id": "s999"},
            {"op": "export_csv", "id": "students.csv"},
            {"op": "consistency_check", "id": "records"},
        ]
    return [
        {"op": "move_file", "src": "inbox/draft.txt", "dst": "work/draft.txt"},
        {"op": "rename_file", "src": "work/draft.txt", "dst": "work/final_report.txt"},
        {"op": "edit_file", "path": "inbox/data.csv", "value": "metric,value\naccuracy,0.82\n"},
        {"op": "generate_summary", "path": "reports/summary.md"},
        {"op": "protect_backup", "path": "backup/draft.txt"},
    ]


def apply_step(state: dict[str, Any], step: dict[str, Any], fault: str | None = None) -> None:
    state["audit"].append({"step": step["op"], "fault": fault or "none"})
    if step["op"] == "create_student":
        target = "s002" if fault == "wrong_object" else step["id"]
        state["records"][target] = dict(step["value"])
        if fault == "extra_side_effect":
            state["records"]["s001"]["status"] = "inactive"
    elif step["op"] == "edit_field":
        target = "s999" if fault == "wrong_object" else step["id"]
        field = "status" if fault == "wrong_field" else step["field"]
        value = "WRONG" if fault == "wrong_content" else step["value"]
        if fault != "non_persistence" and target in state["records"]:
            state["records"][target][field] = value
        if fault == "extra_side_effect":
            state["records"]["s003"] = {"name": "Ghost", "grade": "F", "status": "pending", "phone": "000"}
    elif step["op"] == "delete_student":
        target = "s001" if fault == "wrong_object" else step["id"]
        if fault != "non_persistence":
            state["records"].pop(target, None)
    elif step["op"] == "export_csv":
        if fault != "non_persistence":
            rows = []
            for sid, rec in sorted(state["records"].items()):
                rows.append(f"{sid},{rec['name']},{rec['grade']},{rec['status']},{rec['phone']}")
            state["exports"][step["id"]] = "\n".join(rows)
    elif step["op"] == "consistency_check":
        if fault == "wrong_content":
            state["exports"]["consistency.txt"] = "failed"
        else:
            state["exports"]["consistency.txt"] = "passed"
    elif step["op"] == "move_file":
        src = "archive/old.txt" if fault == "wrong_object" else step["src"]
        dst = "tmp/draft.txt" if fault == "wrong_destination" else step["dst"]
        if fault != "non_persistence" and src in state["files"]:
            state["files"][dst] = state["files"].pop(src)
    elif step["op"] == "rename_file":
        src = "archive/old.txt" if fault == "wrong_object" else step["src"]
        dst = "work/wrong_name.txt" if fault == "wrong_destination" else step["dst"]
        if fault != "non_persistence" and src in state["files"]:
            state["files"][dst] = state["files"].pop(src)
        if fault == "extra_side_effect":
            state["files"].pop("backup/draft.txt", None)
    elif step["op"] == "edit_file":
        path = "archive/old.txt" if fault == "wrong_object" else step["path"]
        value = "metric,value\naccuracy,0.18\n" if fault == "wrong_content" else step["value"]
        if fault != "non_persistence" and path in state["files"]:
            state["files"][path] = value
    elif step["op"] == "generate_summary":
        if fault != "non_persistence":
            acc = "0.82" if "accuracy,0.82" in state["files"].get("inbox/data.csv", "") else "unknown"
            state["reports"][step["path"]] = f"Final report generated. accuracy={acc}"
    elif step["op"] == "protect_backup":
        if fault == "extra_side_effect":
            state["files"].pop(step["path"], None)
        elif step["path"] not in state["files"]:
            state["files"][step["path"]] = "restored backup"


def verify_step(state: dict[str, Any], step: dict[str, Any], before: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if step["op"] == "create_student":
        if state["records"].get(step["id"]) != step["value"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "edit_field":
        if state["records"].get(step["id"], {}).get(step["field"]) != step["value"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "delete_student":
        if step["id"] in state["records"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "export_csv":
        if step["id"] not in state["exports"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "consistency_check":
        if state["exports"].get("consistency.txt") != "passed":
            problems.append("target_unsatisfied")
    elif step["op"] == "move_file":
        if step["dst"] not in state["files"] or step["src"] in state["files"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "rename_file":
        if step["dst"] not in state["files"] or step["src"] in state["files"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "edit_file":
        if state["files"].get(step["path"]) != step["value"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "generate_summary":
        if step["path"] not in state["reports"]:
            problems.append("target_unsatisfied")
    elif step["op"] == "protect_backup":
        if step["path"] not in state["files"]:
            problems.append("target_unsatisfied")

    if state.get("records"):
        before_ids = set(before.get("records", {}))
        after_ids = set(state.get("records", {}))
        allowed_new = {step.get("id")} if step["op"] == "create_student" else set()
        allowed_del = {step.get("id")} if step["op"] == "delete_student" else set()
        allowed_changed = {step.get("id")} if step["op"] in {"create_student", "edit_field", "delete_student"} else set()
        if (after_ids - before_ids) - allowed_new:
            problems.append("extra_side_effect")
        if (before_ids - after_ids) - allowed_del:
            problems.append("extra_side_effect")
        for rid in (before_ids & after_ids) - allowed_changed:
            if before["records"][rid] != state["records"][rid]:
                problems.append("extra_side_effect")
    if state.get("files"):
        before_files = set(before.get("files", {}))
        after_files = set(state.get("files", {}))
        allowed_new = {step.get("dst")} if step["op"] in {"move_file", "rename_file"} else set()
        allowed_del = {step.get("src")} if step["op"] in {"move_file", "rename_file"} else set()
        allowed_changed = {step.get("path")} if step["op"] in {"edit_file", "protect_backup"} else set()
        if step["op"] == "generate_summary":
            allowed_new = {step.get("path")}
            allowed_changed = set()
        if (after_files - before_files) - allowed_new:
            problems.append("extra_side_effect")
        if (before_files - after_files) - allowed_del:
            problems.append("extra_side_effect")
        for rel in (before_files & after_files) - allowed_changed:
            if before["files"][rel] != state["files"][rel]:
                problems.append("extra_side_effect")
    return sorted(set(problems))


def final_oracle(workflow: str, state: dict[str, Any]) -> tuple[bool, bool]:
    initial = initial_state(workflow)
    gold = deepcopy(initial)
    for step in workflow_steps(workflow):
        apply_step(gold, step, None)
    target_satisfied, residue = transition_outcome(initial, gold, state)
    return target_satisfied and not residue, residue


def repair_step(state: dict[str, Any], workflow: str, step: dict[str, Any]) -> tuple[bool, int]:
    before = deepcopy(state)
    if step["op"] in {"create_student", "edit_field", "delete_student", "export_csv", "consistency_check"}:
        if step["op"] == "create_student":
            state["records"][step["id"]] = dict(step["value"])
        elif step["op"] == "edit_field":
            state["records"].setdefault(step["id"], {})[step["field"]] = step["value"]
        elif step["op"] == "delete_student":
            state["records"].pop(step["id"], None)
        else:
            apply_step(state, step, None)
    else:
        apply_step(state, step, None)
    return stable_hash(state) != stable_hash(before), 1


def sample_fault(rng: random.Random, step_index: int) -> str | None:
    choices = [None, None, "wrong_object", "wrong_content", "non_persistence", "extra_side_effect"]
    if step_index in {0, 1}:
        choices.append("wrong_destination")
    if step_index == 2:
        choices.append("wrong_field")
    return rng.choice(choices)


def run_case(workflow: str, method: str, seed: int) -> dict[str, Any]:
    fault_rng = random.Random(10_000 + seed * 17 + WORKFLOWS.index(workflow))
    recovery_rng = random.Random(
        20_000 + seed * 31 + METHODS.index(method) * 101 + WORKFLOWS.index(workflow)
    )
    state = initial_state(workflow)
    initial = deepcopy(state)
    intermediate_deviations = 0
    repair_count = 0
    rollback_count = 0
    rollback_scope_size = 0
    reflection_retries = 0
    token_cost = 600
    steps = workflow_steps(workflow)
    faults = [sample_fault(fault_rng, idx) for idx in range(len(steps))]

    for idx, (step, fault) in enumerate(zip(steps, faults)):
        before = deepcopy(state)
        apply_step(state, step, fault)
        problems = verify_step(state, step, before)
        if problems:
            intermediate_deviations += 1
        if method == "NoCheck":
            continue
        if method == "ReflectionRetry" and problems:
            reflection_retries += 1
            token_cost += 900
            state = deepcopy(before)
            apply_step(state, step, None if recovery_rng.random() < 0.62 else fault)
            continue
        if method == "C-SDVR" and problems:
            rollback_count += 1
            rollback_scope_size += changed_leaf_count(before, state)
            state = deepcopy(before)
            changed, cost = repair_step(state, workflow, step)
            repair_count += cost if changed else 0
            token_cost += 520
        elif method == "FinalVerifier":
            token_cost += 80

    if method == "FinalVerifier":
        ok, residue = final_oracle(workflow, state)
        if not ok or residue:
            repair_count += 1
            token_cost += 1300
            state = deepcopy(initial)
            for step in steps:
                apply_step(state, step, None)
    gold = deepcopy(initial)
    for step in steps:
        apply_step(gold, step, None)
    target_satisfied, residue = transition_outcome(initial, gold, state)
    success = target_satisfied and not residue
    return {
        "workflow_id": workflow,
        "method": method,
        "seed": seed,
        "steps": len(steps),
        "workflow_success": success,
        "success": success,
        "target_satisfied": target_satisfied,
        "intermediate_residue": intermediate_deviations,
        "intermediate_deviations": intermediate_deviations,
        "final_residue": residue,
        "error_accumulation_rate": intermediate_deviations / len(steps),
        "repair_count": repair_count,
        "rollback_count": rollback_count,
        "rollback_scope_size": rollback_scope_size,
        "reflection_retries": reflection_retries,
        "token_cost": token_cost,
        "time_cost": round(0.4 + 0.08 * len(steps) + 0.12 * repair_count + 0.15 * rollback_count, 3),
        "fault_count": sum(fault is not None for fault in faults),
        "fault_sequence_hash": stable_hash(faults),
        "final_state_hash": stable_hash(state),
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["workflow_id"], row["method"])].append(row)
    out: list[dict[str, Any]] = []
    for (workflow, method), vals in sorted(groups.items()):
        out.append(
            {
                "workflow_id": workflow,
                "method": method,
                "runs": len(vals),
                "workflow_success": mean(float(v["workflow_success"]) for v in vals),
                "final_residue": mean(float(v["final_residue"]) for v in vals),
                "intermediate_residue": mean(float(v["intermediate_residue"]) for v in vals),
                "intermediate_deviations": mean(float(v["intermediate_deviations"]) for v in vals),
                "error_accumulation_rate": mean(float(v["error_accumulation_rate"]) for v in vals),
                "repair_count": mean(float(v["repair_count"]) for v in vals),
                "rollback_count": mean(float(v["rollback_count"]) for v in vals),
                "rollback_scope_size": mean(float(v["rollback_scope_size"]) for v in vals),
                "token_cost": mean(float(v["token_cost"]) for v in vals),
                "time_cost": mean(float(v["time_cost"]) for v in vals),
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(summary: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    agg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        agg[row["method"]].append(row)
    lines = [
        "# Workflow Validation v4",
        "",
        f"Raw runs: {len(rows)}",
        "",
        "| Method | Runs | Success | Final residue | Intermediate deviations | Repair | Rollback | Token |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        vals = agg[method]
        lines.append(
            f"| {method} | {len(vals)} | {mean(float(v['workflow_success']) for v in vals):.3f} | "
            f"{mean(float(v['final_residue']) for v in vals):.3f} | "
            f"{mean(float(v['intermediate_residue']) for v in vals):.2f} | "
            f"{mean(float(v['repair_count']) for v in vals):.2f} | "
            f"{mean(float(v['rollback_count']) for v in vals):.2f} | "
            f"{mean(float(v['token_cost']) for v in vals):.1f} |"
        )
    lines.extend(
        [
            "",
            "Per-workflow summary rows are stored in `workflow_validation_summary_v4.csv`.",
            "Rollback-depth rows are stored in `workflow_rollback_depth_v4.csv`.",
            "A narrative local-repair trace is stored in `workflow_case_study_v4.md`.",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n")


def write_rollback_depth(rows: list[dict[str, Any]]) -> None:
    out = []
    for row in rows:
        out.append(
            {
                "workflow_id": row["workflow_id"],
                "method": row["method"],
                "seed": row["seed"],
                "rollback_count": row["rollback_count"],
                "rollback_scope_size": row["rollback_scope_size"],
                "repair_count": row["repair_count"],
                "token_cost": row["token_cost"],
                "final_residue": row["final_residue"],
                "workflow_success": row["workflow_success"],
            }
        )
    write_csv(ROLLBACK_DEPTH, out)


def write_case_study() -> None:
    workflow = "student_records"
    state = initial_state(workflow)
    steps = workflow_steps(workflow)
    faults = ["none", "extra_side_effect", "wrong_field", "none", "non_persistence", "none"]
    trace = []
    csdvr_state = deepcopy(state)
    final_state = deepcopy(state)
    for idx, (step, fault) in enumerate(zip(steps, faults), start=1):
        before = deepcopy(csdvr_state)
        apply_step(csdvr_state, step, None if fault == "none" else fault)
        problems = verify_step(csdvr_state, step, before)
        action = "continue"
        rollback_scope = 0
        if problems:
            rollback_scope = len(json.dumps(before, sort_keys=True)) // 80
            csdvr_state = deepcopy(before)
            repair_step(csdvr_state, workflow, step)
            action = "local rollback + bounded repair"
        trace.append(
            {
                "step": idx,
                "operation": step["op"],
                "fault": fault,
                "detected": bool(problems),
                "problems": ";".join(problems) if problems else "none",
                "csdvr_action": action,
                "rollback_scope": rollback_scope,
            }
        )
    for step in steps:
        apply_step(final_state, step, None)
    csdvr_success, csdvr_residue = final_oracle(workflow, csdvr_state)
    final_success, final_residue = final_oracle(workflow, final_state)
    lines = [
        "# Workflow Case Study v4",
        "",
        "This trace uses the `student_records` workflow to show how local recovery prevents error accumulation.",
        "",
        "| Step | Operation | Injected fault | Detected | Problem | C-SDVR action | Rollback scope |",
        "|---:|---|---|---|---|---|---:|",
    ]
    for row in trace:
        lines.append(
            f"| {row['step']} | {row['operation']} | {row['fault']} | {row['detected']} | "
            f"{row['problems']} | {row['csdvr_action']} | {row['rollback_scope']} |"
        )
    lines.extend(
        [
            "",
            "FinalVerifier comparison: the final-only policy detects failure at workflow end, restores the initial snapshot, and replays all six steps. This is intentionally strong because it assumes a full-workflow snapshot and a clean replay plan.",
            f"C-SDVR final success/residue: {csdvr_success}/{csdvr_residue}.",
            f"Final full-replay success/residue: {final_success}/{final_residue}.",
            "Interpretation: C-SDVR does not need to replay unaffected steps; it restores only the pre-step scoped state and repairs the bounded target.",
        ]
    )
    CASE_STUDY.write_text("\n".join(lines) + "\n")


def main() -> None:
    rows = [run_case(workflow, method, seed) for workflow in WORKFLOWS for method in METHODS for seed in SEEDS]
    summary = summarize(rows)
    write_csv(RAW, rows)
    write_csv(SUMMARY, summary)
    write_rollback_depth(rows)
    write_case_study()
    write_report(summary, rows)
    print(f"workflow_runs={len(rows)}")
    print(RAW)
    print(SUMMARY)
    print(REPORT)
    print(ROLLBACK_DEPTH)
    print(CASE_STUDY)


if __name__ == "__main__":
    main()
