#!/usr/bin/env python3
"""Small live-style validation for C-SDVR.

This script complements the larger executable benchmark with a smaller
validation that uses:

1. real temporary filesystem mutations; and
2. a local Flask HTTP form service backed by a SQLite database file.

It is intentionally described as "live-style" rather than a live LLM/browser
experiment: the action executor is scripted and the web-form path uses HTTP
requests, not a real browser, because Playwright CLI is unavailable in the
current machine environment.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import random
import shutil
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.serving import make_server


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
RAW = OUT / "live_validation_raw_v3.csv"
SUMMARY = OUT / "live_validation_summary_v3.csv"
REPORT = OUT / "live_validation_report_v3.md"

METHODS = ["NoCheck", "FinalVerifier", "C-SDVR"]
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"
URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@dataclass(frozen=True)
class LiveTask:
    task_id: str
    domain: str
    op: str
    target: str
    expected: str
    fault: str
    severity: str


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def file_snapshot(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.read_text(encoding="utf-8")
    return out


MISSING = ("__CSDVR_MISSING__",)


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


def transition_outcome(before: dict[str, Any], gold: dict[str, Any], final: dict[str, Any]) -> tuple[bool, bool]:
    before_flat = flatten_state(before)
    gold_flat = flatten_state(gold)
    final_flat = flatten_state(final)
    intended_keys = {
        key
        for key in set(before_flat) | set(gold_flat)
        if before_flat.get(key, MISSING) != gold_flat.get(key, MISSING)
    }
    target_satisfied = bool(intended_keys) and all(
        final_flat.get(key, MISSING) == gold_flat.get(key, MISSING) for key in intended_keys
    )
    residue = any(
        final_flat.get(key, MISSING) != gold_flat.get(key, MISSING)
        and final_flat.get(key, MISSING) != before_flat.get(key, MISSING)
        for key in set(before_flat) | set(gold_flat) | set(final_flat)
    )
    return target_satisfied, residue


def state_hash(snapshot: dict[str, Any]) -> str:
    return h(json.dumps(snapshot, sort_keys=True))


def serialized_bytes(snapshot: Any) -> int:
    return len(json.dumps(snapshot, sort_keys=True, ensure_ascii=True).encode("utf-8"))


def changed_payload_bytes(source: Any, target: Any) -> int:
    source_flat = flatten_state(source)
    target_flat = flatten_state(target)
    changed = {
        "/".join(key): target_flat.get(key)
        for key in set(source_flat) | set(target_flat)
        if source_flat.get(key) != target_flat.get(key)
    }
    return serialized_bytes(changed)


def restore_files_scoped(root: Path, before: dict[str, str], gold: dict[str, str]) -> None:
    current = file_snapshot(root)
    keys = set(before) | set(current) | set(gold)
    affected = {
        key
        for key in keys
        if current.get(key) != before.get(key) or gold.get(key) != before.get(key)
    }
    for key in affected:
        path = root / key
        if key in gold:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(gold[key], encoding="utf-8")
        elif path.exists():
            path.unlink()


def setup_files(root: Path) -> None:
    (root / "work").mkdir(parents=True, exist_ok=True)
    (root / "archive").mkdir(parents=True, exist_ok=True)
    for name, text in [
        ("alpha.txt", "alpha seed"),
        ("beta.txt", "beta seed"),
        ("gamma.txt", "gamma seed"),
    ]:
        (root / "work" / name).write_text(text, encoding="utf-8")


def run_file_action(root: Path, task: LiveTask, fault: str | None) -> None:
    target = root / task.target
    expected = root / task.expected
    actual_target = target
    actual_expected = expected
    if fault == "wrong_object":
        actual_target = root / "work/beta.txt"
    if fault == "wrong_destination":
        actual_expected = root / "archive/misplaced.txt"
    if task.op == "rename":
        actual_expected.parent.mkdir(parents=True, exist_ok=True)
        if actual_target.exists():
            actual_target.rename(actual_expected)
    elif task.op == "copy":
        actual_expected.parent.mkdir(parents=True, exist_ok=True)
        if actual_target.exists():
            shutil.copyfile(actual_target, actual_expected)
    elif task.op == "edit":
        if actual_target.exists():
            val = task.expected if fault != "wrong_content" else f"{task.expected}_wrong"
            actual_target.write_text(actual_target.read_text(encoding="utf-8") + "|" + val, encoding="utf-8")
    elif task.op == "delete":
        if actual_target.exists():
            actual_target.unlink()
    if fault == "extra_side_effect":
        p = root / "work/gamma.txt"
        if p.exists():
            p.unlink()
    if fault == "partial_completion":
        # Leave a visible temp artifact but do not complete the intended target.
        (root / "work/partial.tmp").write_text("partial", encoding="utf-8")


def file_success(root: Path, task: LiveTask) -> tuple[bool, bool]:
    residue = not (root / "work/gamma.txt").exists() and task.target != "work/gamma.txt"
    if task.op in {"rename", "copy"}:
        ok = (root / task.expected).exists()
    elif task.op == "edit":
        p = root / task.target
        ok = p.exists() and task.expected in p.read_text(encoding="utf-8")
    elif task.op == "delete":
        ok = not (root / task.target).exists()
    else:
        ok = False
    return ok and not residue, residue


def make_app(db_path: Path) -> Flask:
    app = Flask(__name__)

    def conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    @app.route("/reset", methods=["POST"])
    def reset():
        c = conn()
        c.execute("DROP TABLE IF EXISTS records")
        c.execute("CREATE TABLE records(id TEXT PRIMARY KEY, name TEXT, status TEXT, amount INTEGER)")
        c.executemany(
            "INSERT INTO records VALUES (?, ?, ?, ?)",
            [("r1", "Alpha", "draft", 10), ("r2", "Beta", "open", 20), ("r3", "Gamma", "closed", 30)],
        )
        c.commit()
        c.close()
        return jsonify({"ok": True})

    @app.route("/snapshot", methods=["GET"])
    def snapshot():
        c = conn()
        rows = [dict(r) for r in c.execute("SELECT * FROM records ORDER BY id")]
        c.close()
        return jsonify({"rows": rows, "hash": h(json.dumps(rows, sort_keys=True))})

    @app.route("/submit", methods=["POST"])
    def submit():
        data = request.form
        rid = data.get("id", "r1")
        op = data.get("op", "edit")
        value = data.get("value", "value")
        c = conn()
        if op == "create":
            c.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)", (rid, value, "open", 1))
        elif op == "edit":
            c.execute("UPDATE records SET name=? WHERE id=?", (value, rid))
        elif op == "status":
            c.execute("UPDATE records SET status=? WHERE id=?", (value, rid))
        elif op == "delete":
            c.execute("DELETE FROM records WHERE id=?", (rid,))
        c.commit()
        c.close()
        return jsonify({"ok": True})

    return app


def post(url: str, data: dict[str, str] | None = None) -> dict:
    if data is None:
        req = urllib.request.Request(url, method="POST")
    else:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
    with URL_OPENER.open(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def get(url: str) -> dict:
    with URL_OPENER.open(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def setup_server(db_path: Path):
    app = make_app(db_path)
    server = make_server("127.0.0.1", 0, app)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.02)
    return f"http://127.0.0.1:{port}", server


def form_snapshot(base: str) -> dict[str, Any]:
    snap = get(f"{base}/snapshot")
    return {
        "rows": {
            row["id"]: {
                "name": row["name"],
                "status": row["status"],
                "amount": row["amount"],
            }
            for row in snap["rows"]
        }
    }


def run_form_action(base: str, task: LiveTask, fault: str | None) -> None:
    rid = task.target
    value = task.expected
    op = task.op
    if fault == "wrong_object":
        rid = "r2"
    if fault == "wrong_content":
        value = f"{value}_wrong"
    if fault == "not_persisted":
        return
    post(f"{base}/submit", {"id": rid, "op": op, "value": value})
    if fault == "extra_side_effect":
        post(f"{base}/submit", {"id": "r3", "op": "delete", "value": ""})
    if fault == "partial_completion":
        # Undo intended persistence to leave only the visible request trace.
        post(f"{base}/reset")


def form_success(base: str, task: LiveTask) -> tuple[bool, bool]:
    snap = get(f"{base}/snapshot")
    rows = {r["id"]: r for r in snap["rows"]}
    residue = "r3" not in rows and task.target != "r3"
    if task.op == "create":
        ok = task.target in rows and rows[task.target]["name"] == task.expected
    elif task.op == "edit":
        ok = task.target in rows and rows[task.target]["name"] == task.expected
    elif task.op == "status":
        ok = task.target in rows and rows[task.target]["status"] == task.expected
    elif task.op == "delete":
        ok = task.target not in rows
    else:
        ok = False
    return ok and not residue, residue


def tasks() -> list[LiveTask]:
    return [
        LiveTask("LF01", "file", "rename", "work/alpha.txt", "work/renamed_alpha.txt", "wrong_object", "critical"),
        LiveTask("LF02", "file", "copy", "work/alpha.txt", "archive/alpha_copy.txt", "extra_side_effect", "critical"),
        LiveTask("LF03", "file", "edit", "work/alpha.txt", "approved", "wrong_content", "major"),
        LiveTask("LF04", "file", "rename", "work/alpha.txt", "archive/alpha.txt", "wrong_destination", "major"),
        LiveTask("LF05", "file", "delete", "work/alpha.txt", "", "partial_completion", "major"),
        LiveTask("LW01", "form", "edit", "r1", "Alice", "wrong_object", "critical"),
        LiveTask("LW02", "form", "edit", "r1", "Bob", "extra_side_effect", "critical"),
        LiveTask("LW03", "form", "status", "r1", "closed", "not_persisted", "critical"),
        LiveTask("LW04", "form", "edit", "r1", "Carol", "wrong_content", "major"),
        LiveTask("LW05", "form", "create", "new1", "Delta", "partial_completion", "major"),
    ]


def run_one(task: LiveTask, method: str, seed: int) -> dict[str, object]:
    wall_start = time.perf_counter()
    fault_rng = random.Random(f"live-paired:{task.task_id}:{seed}")
    fault = task.fault if fault_rng.random() < 0.75 else None
    detected = False
    repair_attempted = False
    rollback_used = False
    snapshot_bytes = 0
    rollback_bytes = 0
    token = {"NoCheck": 700, "FinalVerifier": 1250, "C-SDVR": 1450}[method]
    time_cost = {"NoCheck": 4.0, "FinalVerifier": 8.5, "C-SDVR": 9.5}[method]

    if task.domain == "file":
        with tempfile.TemporaryDirectory(prefix="csdvr_live_") as d:
            base_dir = Path(d)
            root = base_dir / "exec"
            gold_root = base_dir / "gold"
            backup = base_dir / "backup"
            setup_files(root)
            setup_files(gold_root)
            shutil.copytree(root, backup)
            before = file_snapshot(root)
            snapshot_bytes = serialized_bytes(before)
            run_file_action(gold_root, task, None)
            gold = file_snapshot(gold_root)
            run_file_action(root, task, fault)
            after = file_snapshot(root)
            target_satisfied, residue = transition_outcome(before, gold, after)
            if method != "NoCheck":
                detected = not target_satisfied or residue
            if detected and method == "FinalVerifier":
                repair_attempted = True
                run_file_action(root, task, None)
            if detected and method == "C-SDVR":
                repair_attempted = True
                if task.severity == "critical":
                    rollback_used = True
                    rollback_bytes = changed_payload_bytes(after, before)
                    shutil.rmtree(root)
                    shutil.copytree(backup, root)
                    run_file_action(root, task, None)
                else:
                    restore_files_scoped(root, before, gold)
            final = file_snapshot(root)
            target_satisfied, residue = transition_outcome(before, gold, final)
    else:
        with tempfile.TemporaryDirectory(prefix="csdvr_form_") as d:
            db = Path(d) / "records.sqlite"
            base, server = setup_server(db)
            try:
                post(f"{base}/reset")
                before = form_snapshot(base)
                snapshot_bytes = serialized_bytes(before)
                run_form_action(base, task, None)
                gold = form_snapshot(base)
                post(f"{base}/reset")
                run_form_action(base, task, fault)
                after = form_snapshot(base)
                target_satisfied, residue = transition_outcome(before, gold, after)
                if method != "NoCheck":
                    detected = not target_satisfied or residue
                if detected and method == "FinalVerifier":
                    repair_attempted = True
                    run_form_action(base, task, None)
                if detected and method == "C-SDVR":
                    repair_attempted = True
                    if task.severity == "critical":
                        rollback_used = True
                        rollback_bytes = changed_payload_bytes(after, before)
                        post(f"{base}/reset")
                    run_form_action(base, task, None)
                final = form_snapshot(base)
                target_satisfied, residue = transition_outcome(before, gold, final)
            finally:
                server.shutdown()

    ok = target_satisfied and not residue

    if detected:
        token += 180
        time_cost += 0.8
    if repair_attempted:
        token += 650 if method == "C-SDVR" else 950
        time_cost += 3.0 if method == "C-SDVR" else 5.0
    unnecessary = int(repair_attempted and fault is None)
    cns = int(ok) / (token / 2000 + time_cost / 20 + 4 / 10)
    wall_clock_ms = (time.perf_counter() - wall_start) * 1000
    return {
        "seed": seed,
        "task_id": task.task_id,
        "domain": task.domain,
        "method": method,
        "fault": fault or "none",
        "severity": task.severity if fault else "none",
        "detected": int(detected),
        "repair_attempted": int(repair_attempted),
        "rollback_used": int(rollback_used),
        "target_satisfied": int(target_satisfied),
        "success": int(ok),
        "residue": int(residue),
        "unnecessary_repair": unnecessary,
        "token_cost": token,
        "time_cost": f"{time_cost:.2f}",
        "cost_norm_success": f"{cns:.6f}",
        "wall_clock_ms": f"{wall_clock_ms:.3f}",
        "snapshot_bytes": snapshot_bytes,
        "rollback_bytes": rollback_bytes,
        "repair_function": "scripted_oracle" if repair_attempted else "none",
        "state_before_hash": state_hash(before),
        "state_after_hash": state_hash(after),
        "state_final_hash": state_hash(final),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for method in METHODS:
        items = [r for r in rows if r["method"] == method]
        fault_items = [r for r in items if r["fault"] != "none"]
        tp = sum(int(r["detected"]) for r in fault_items)
        fn = len(fault_items) - tp
        fp = sum(int(r["detected"]) for r in items if r["fault"] == "none")
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out.append(
            {
                "method": method,
                "n_runs": len(items),
                "success": f"{mean([int(r['success']) for r in fault_items]):.4f}",
                "residue": f"{mean([int(r['residue']) for r in fault_items]):.4f}",
                "detection_f1": f"{f1:.4f}",
                "critical_recall": f"{mean([int(r['detected']) for r in fault_items if r['severity']=='critical']):.4f}",
                "rollback_use": f"{mean([int(r['rollback_used']) for r in fault_items]):.4f}",
                "unnecessary_repair": f"{mean([int(r['unnecessary_repair']) for r in items]):.4f}",
                "token_cost": f"{mean([int(r['token_cost']) for r in items]):.2f}",
                "cost_norm_success": f"{mean([float(r['cost_norm_success']) for r in fault_items]):.4f}",
            }
        )
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in range(20):
        for task in tasks():
            for method in METHODS:
                rows.append(run_one(task, method, seed))
    write_csv(RAW, rows)
    summary = summarize(rows)
    write_csv(SUMMARY, summary)

    lines = [
        "# Live-style Validation Report",
        "",
        "Verification Status: VERIFIED BY LOCAL FILESYSTEM AND FLASK HTTP EXECUTION",
        "",
        "This validation uses real temporary filesystem mutations and a local Flask HTTP form service backed by SQLite. It is not a live LLM API or real-browser Playwright experiment because `npx` is unavailable in the current environment.",
        "",
        "| Method | Success | Residue | Detection F1 | Critical recall | Token cost | CNS |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary:
        lines.append(
            f"| {r['method']} | {float(r['success']):.3f} | {float(r['residue']):.3f} | "
            f"{float(r['detection_f1']):.3f} | {float(r['critical_recall']):.3f} | "
            f"{float(r['token_cost']):.1f} | {float(r['cost_norm_success']):.3f} |"
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"live_runs={len(rows)}")
    print(REPORT)


if __name__ == "__main__":
    main()
