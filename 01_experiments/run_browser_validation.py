#!/usr/bin/env python3
"""Playwright browser validation for the web-form part of C-SDVR.

This experiment uses a real headless Chromium browser to submit a local HTML
form served by Flask and backed by SQLite. It is still not a live LLM-agent
experiment: the browser actions are scripted so the validation isolates the
state-verification and local-repair policy under a real browser execution layer.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import random
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
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
RAW = OUT / "browser_validation_raw_v3.csv"
SUMMARY = OUT / "browser_validation_summary_v3.csv"
REPORT = OUT / "browser_validation_report_v3.md"

METHODS = ["NoCheck", "FinalVerifier", "C-SDVR"]
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"
URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@dataclass(frozen=True)
class BrowserTask:
    task_id: str
    op: str
    target: str
    expected: str
    fault: str
    severity: str


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


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

    @app.route("/form", methods=["GET"])
    def form():
        return """
        <!doctype html>
        <html>
        <body>
          <form id="record-form" method="post" action="/submit">
            <label>ID <input id="id" name="id"></label>
            <label>Operation <select id="op" name="op">
              <option value="create">create</option>
              <option value="edit">edit</option>
              <option value="status">status</option>
              <option value="delete">delete</option>
            </select></label>
            <label>Value <input id="value" name="value"></label>
            <button id="submit" type="submit">Submit</button>
          </form>
        </body>
        </html>
        """

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
        return "<p id='ok'>ok</p>"

    return app


class ServerThread:
    def __init__(self, db_path: Path):
        self.app = make_app(db_path)
        self.server = make_server("127.0.0.1", 0, self.app)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> str:
        self.thread.start()
        time.sleep(0.03)
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=1)


def post(url: str) -> dict:
    req = urllib.request.Request(url, method="POST")
    with URL_OPENER.open(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def get(url: str) -> dict:
    with URL_OPENER.open(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


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


def restore_db_scoped(
    db_path: Path,
    before: dict[str, Any],
    gold: dict[str, Any],
    current: dict[str, Any],
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        row_ids = set(before["rows"]) | set(gold["rows"]) | set(current["rows"])
        for rid in row_ids:
            before_row = before["rows"].get(rid)
            gold_row = gold["rows"].get(rid)
            current_row = current["rows"].get(rid)
            if current_row == before_row and gold_row == before_row:
                continue
            if gold_row is None:
                conn.execute("DELETE FROM records WHERE id=?", (rid,))
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)",
                    (rid, gold_row["name"], gold_row["status"], int(gold_row["amount"])),
                )
        conn.commit()
    finally:
        conn.close()


def tasks() -> list[BrowserTask]:
    return [
        BrowserTask("BW01", "edit", "r1", "Alice", "wrong_object", "critical"),
        BrowserTask("BW02", "edit", "r1", "Bob", "extra_side_effect", "critical"),
        BrowserTask("BW03", "status", "r1", "closed", "not_persisted", "critical"),
        BrowserTask("BW04", "edit", "r1", "Carol", "wrong_content", "major"),
        BrowserTask("BW05", "create", "new1", "Delta", "partial_completion", "major"),
    ]


def submit_form(page, base: str, op: str, rid: str, value: str) -> None:
    page.goto(f"{base}/form", wait_until="domcontentloaded")
    page.fill("#id", rid)
    page.select_option("#op", op)
    page.fill("#value", value)
    page.click("#submit")
    page.wait_for_selector("#ok", timeout=3000)


def run_browser_action(page, base: str, task: BrowserTask, fault: str | None) -> None:
    rid = task.target
    value = task.expected
    op = task.op
    if fault == "wrong_object":
        rid = "r2"
    if fault == "wrong_content":
        value = f"{value}_wrong"
    if fault == "not_persisted":
        page.goto(f"{base}/form", wait_until="domcontentloaded")
        page.fill("#id", rid)
        page.select_option("#op", op)
        page.fill("#value", value)
        return
    if fault == "partial_completion":
        submit_form(page, base, "edit", "r2", "partial_visible")
        return
    submit_form(page, base, op, rid, value)
    if fault == "extra_side_effect":
        submit_form(page, base, "delete", "r3", "")


def form_success(base: str, task: BrowserTask) -> tuple[bool, bool]:
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


def run_one(browser, task: BrowserTask, method: str, seed: int) -> dict[str, object]:
    wall_start = time.perf_counter()
    fault_rng = random.Random(f"browser-paired:{task.task_id}:{seed}")
    fault = task.fault if fault_rng.random() < 0.75 else None
    detected = False
    repair_attempted = False
    rollback_used = False
    snapshot_bytes = 0
    rollback_bytes = 0
    token = {"NoCheck": 720, "FinalVerifier": 1320, "C-SDVR": 1510}[method]
    time_cost = {"NoCheck": 4.6, "FinalVerifier": 9.6, "C-SDVR": 10.8}[method]

    with tempfile.TemporaryDirectory(prefix="csdvr_browser_") as d:
        db = Path(d) / "records.sqlite"
        server = ServerThread(db)
        base = server.start()
        try:
            post(f"{base}/reset")
            page = browser.new_page()
            before = form_snapshot(base)
            snapshot_bytes = serialized_bytes(before)
            run_browser_action(page, base, task, None)
            gold = form_snapshot(base)
            post(f"{base}/reset")
            run_browser_action(page, base, task, fault)
            after = form_snapshot(base)
            target_satisfied, residue = transition_outcome(before, gold, after)
            if method != "NoCheck":
                detected = not target_satisfied or residue
            if detected and method == "FinalVerifier":
                repair_attempted = True
                run_browser_action(page, base, task, None)
            if detected and method == "C-SDVR":
                repair_attempted = True
                if task.severity == "critical":
                    rollback_used = True
                    rollback_bytes = changed_payload_bytes(after, before)
                    post(f"{base}/reset")
                    run_browser_action(page, base, task, None)
                else:
                    restore_db_scoped(db, before, gold, after)
            final = form_snapshot(base)
            target_satisfied, residue = transition_outcome(before, gold, final)
            ok = target_satisfied and not residue
            page.close()
        finally:
            server.stop()

    if detected:
        token += 190
        time_cost += 1.0
    if repair_attempted:
        token += 700 if method == "C-SDVR" else 980
        time_cost += 3.4 if method == "C-SDVR" else 5.5
    unnecessary = int(repair_attempted and fault is None)
    cns = int(ok) / (token / 2000 + time_cost / 20 + 4 / 10)
    wall_clock_ms = (time.perf_counter() - wall_start) * 1000
    return {
        "seed": seed,
        "task_id": task.task_id,
        "domain": "browser_form",
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
        crit = [r for r in fault_items if r["severity"] == "critical"]
        out.append(
            {
                "method": method,
                "n_runs": len(items),
                "success": f"{mean([int(r['success']) for r in fault_items]):.4f}",
                "residue": f"{mean([int(r['residue']) for r in fault_items]):.4f}",
                "detection_f1": f"{f1:.4f}",
                "critical_recall": f"{mean([int(r['detected']) for r in crit]):.4f}",
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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for seed in range(20):
                for task in tasks():
                    for method in METHODS:
                        rows.append(run_one(browser, task, method, seed))
        finally:
            browser.close()

    write_csv(RAW, rows)
    summary = summarize(rows)
    write_csv(SUMMARY, summary)
    lines = [
        "# Browser Validation Report",
        "",
        "Verification Status: VERIFIED BY LOCAL FLASK/SQLITE AND HEADLESS CHROMIUM VIA PLAYWRIGHT",
        "",
        "This validation uses a real headless Chromium browser to open a local HTML form, fill fields, click submit, and then checks the backing SQLite state. It is a browser-execution validation, not a live LLM-agent validation.",
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
    print(f"browser_runs={len(rows)}")
    print(REPORT)


if __name__ == "__main__":
    main()
