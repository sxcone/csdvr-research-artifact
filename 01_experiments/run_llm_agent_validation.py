#!/usr/bin/env python3
"""Small live LLM-agent validation for C-SDVR.

This script runs a bounded real-agent validation against an OpenAI-compatible
chat-completions endpoint. The model chooses JSON actions for real temporary
filesystem tasks and local browser-submitted Flask/SQLite form tasks.

Required environment variables:
  CSDVR_LLM_BASE_URL   e.g. http://127.0.0.1:1234/v1
  CSDVR_LLM_MODEL      e.g. local-model-name
  CSDVR_LLM_API_KEY    use a dummy value only if the local server accepts it

The script intentionally exits without writing benchmark results when the
environment is not configured. It should not be replaced by simulated results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
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
RAW = OUT / "llm_agent_validation_raw_v3.csv"
SUMMARY = OUT / "llm_agent_validation_summary_v3.csv"
REPORT = OUT / "llm_agent_validation_report_v3.md"
SMOKE_RAW = OUT / "llm_agent_validation_smoke_raw_v3.csv"
SMOKE_SUMMARY = OUT / "llm_agent_validation_smoke_summary_v3.csv"
SMOKE_REPORT = OUT / "llm_agent_validation_smoke_report_v3.md"

METHODS = ["NoCheck", "FinalVerifier", "C-SDVR"]
ALLOWED_FILE_OPS = {"rename", "edit", "move", "copy", "delete", "create"}
ALLOWED_FORM_OPS = {"edit", "status", "create", "delete"}
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"


@dataclass(frozen=True)
class AgentTask:
    task_id: str
    domain: str
    op: str
    target: str
    expected: str
    destination: str
    severity: str
    instruction: str


@dataclass
class LLMResult:
    action: dict[str, Any] | None
    tokens: int
    token_source: str
    invalid_json_count: int
    raw_text: str
    error: str


def h(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def require_env() -> tuple[str, str, str]:
    missing = [k for k in ("CSDVR_LLM_BASE_URL", "CSDVR_LLM_MODEL", "CSDVR_LLM_API_KEY") if not os.getenv(k)]
    if missing:
        msg = (
            "Missing required LLM endpoint configuration: "
            + ", ".join(missing)
            + "\nSet CSDVR_LLM_BASE_URL, CSDVR_LLM_MODEL, and CSDVR_LLM_API_KEY before running."
        )
        raise SystemExit(msg)
    return (
        os.environ["CSDVR_LLM_BASE_URL"].rstrip("/"),
        os.environ["CSDVR_LLM_MODEL"],
        os.environ["CSDVR_LLM_API_KEY"],
    )


class OpenAICompatibleClient:
    def __init__(self, base_url: str, model: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def chat(self, messages: list[dict[str, str]]) -> tuple[str, int, str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 280,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        timeout = float(os.getenv("CSDVR_LLM_TIMEOUT", "90"))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Connection error: {e}") from e

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        if "total_tokens" in usage:
            return content, int(usage["total_tokens"]), "actual"
        approx = max(1, (sum(len(m["content"]) for m in messages) + len(content)) // 4)
        return content, approx, "estimated"


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found")
    obj = json.loads(stripped[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON value is not an object")
    return obj


def ask_for_action(client: OpenAICompatibleClient, task: AgentTask, state: Any, repair_context: str | None = None) -> LLMResult:
    if task.domain == "file":
        schema = (
            '{"domain":"file","op":"rename|edit|move|copy|delete|create",'
            '"target":"relative/path","value":"text if needed","destination":"relative/path if needed"}'
        )
    else:
        schema = '{"domain":"web_form","op":"edit|status|create|delete","id":"record id","value":"text if needed"}'
    system = (
        "You are an action executor for a bounded local test environment. "
        "Return exactly one JSON object and no prose. Do not use paths outside the workspace. "
        f"Allowed schema: {schema}."
    )
    user = {
        "task_id": task.task_id,
        "instruction": task.instruction,
        "current_state": state,
    }
    if repair_context:
        user["repair_context"] = repair_context
    messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, sort_keys=True)}]

    total_tokens = 0
    token_source = "actual"
    invalid = 0
    raw = ""
    error = ""
    for attempt in range(3):
        try:
            raw, tokens, source = client.chat(messages)
            total_tokens += tokens
            if source == "estimated":
                token_source = "estimated"
            action = extract_json_object(raw)
            return LLMResult(action, total_tokens, token_source, invalid, raw, "")
        except Exception as exc:  # JSON repair retry or endpoint error.
            error = str(exc)
            if "HTTP " in error or "Connection error" in error:
                return LLMResult(None, total_tokens, token_source, invalid, raw, error)
            invalid += 1
            if attempt == 2:
                break
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The previous response was invalid because: "
                        f"{error}. Return only a valid JSON object matching the schema."
                    ),
                }
            )
    return LLMResult(None, total_tokens, token_source, invalid, raw, error)


def safe_rel_path(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel:
        raise ValueError("missing relative path")
    p = (root / rel).resolve()
    if root.resolve() not in p.parents and p != root.resolve():
        raise ValueError(f"path escapes root: {rel}")
    return p


def setup_files(root: Path) -> None:
    (root / "work").mkdir(parents=True, exist_ok=True)
    (root / "archive").mkdir(parents=True, exist_ok=True)
    initial = {
        "work/alpha.txt": "alpha seed",
        "work/beta.txt": "beta seed",
        "work/gamma.txt": "gamma seed",
        "work/obsolete.txt": "remove me",
        "work/config.txt": "mode=dev",
        "work/report_draft.md": "draft report",
        "work/temp.tmp": "temporary",
    }
    for rel, text in initial.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def file_content_snapshot(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.read_text(encoding="utf-8")
    return out


def expected_file_snapshot(before: dict[str, str], task: AgentTask) -> dict[str, str]:
    after = dict(before)
    if task.op in {"rename", "move"}:
        if task.target in after:
            after[task.destination] = after.pop(task.target)
    elif task.op == "copy":
        if task.target in after:
            after[task.destination] = after[task.target]
    elif task.op in {"edit", "create"}:
        after[task.target] = task.expected
    elif task.op == "delete":
        after.pop(task.target, None)
    return after


def execute_file_action(root: Path, action: dict[str, Any]) -> tuple[bool, str]:
    try:
        if action.get("domain") != "file":
            raise ValueError("domain must be file")
        op = str(action.get("op", ""))
        if op not in ALLOWED_FILE_OPS:
            raise ValueError(f"unsupported file op: {op}")
        target = safe_rel_path(root, str(action.get("target", "")))
        destination = action.get("destination") or ""
        value = str(action.get("value", ""))
        if op in {"rename", "move"}:
            dest = safe_rel_path(root, str(destination))
            dest.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.rename(dest)
        elif op == "copy":
            dest = safe_rel_path(root, str(destination))
            dest.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.copyfile(target, dest)
        elif op == "edit":
            if target.exists():
                target.write_text(value, encoding="utf-8")
        elif op == "create":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        elif op == "delete":
            if target.exists():
                target.unlink()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def make_app(db_path: Path) -> Flask:
    app = Flask(__name__)

    def conn() -> sqlite3.Connection:
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
        return jsonify({"rows": rows})

    @app.route("/form", methods=["GET"])
    def form():
        return """
        <!doctype html>
        <html><body>
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
        </body></html>
        """

    @app.route("/submit", methods=["POST"])
    def submit():
        data = request.form
        rid = data.get("id", "r1")
        op = data.get("op", "edit")
        value = data.get("value", "")
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


def http_post(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def form_rows(base: str) -> dict[str, dict[str, Any]]:
    snap = http_get(f"{base}/snapshot")
    return {r["id"]: r for r in snap["rows"]}


def expected_form_rows(before: dict[str, dict[str, Any]], task: AgentTask) -> dict[str, dict[str, Any]]:
    after = json.loads(json.dumps(before))
    if task.op == "create":
        after[task.target] = {"id": task.target, "name": task.expected, "status": "open", "amount": 1}
    elif task.op == "edit" and task.target in after:
        after[task.target]["name"] = task.expected
    elif task.op == "status" and task.target in after:
        after[task.target]["status"] = task.expected
    elif task.op == "delete":
        after.pop(task.target, None)
    return after


def submit_form(page, base: str, op: str, rid: str, value: str) -> None:
    page.goto(f"{base}/form", wait_until="domcontentloaded")
    page.fill("#id", rid)
    page.select_option("#op", op)
    page.fill("#value", value)
    page.click("#submit")
    page.wait_for_selector("#ok", timeout=3000)


def execute_form_action(page, base: str, action: dict[str, Any]) -> tuple[bool, str]:
    try:
        if action.get("domain") not in {"web_form", "form"}:
            raise ValueError("domain must be web_form")
        op = str(action.get("op", ""))
        if op not in ALLOWED_FORM_OPS:
            raise ValueError(f"unsupported form op: {op}")
        rid = str(action.get("id", ""))
        if not rid:
            raise ValueError("missing record id")
        value = str(action.get("value", ""))
        submit_form(page, base, op, rid, value)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def all_tasks() -> list[AgentTask]:
    return [
        AgentTask("LLMF01", "file", "rename", "work/alpha.txt", "", "work/alpha_renamed.txt", "critical", "Rename work/alpha.txt to work/alpha_renamed.txt."),
        AgentTask("LLMF02", "file", "edit", "work/beta.txt", "approved", "", "major", "Set the content of work/beta.txt to approved."),
        AgentTask("LLMF03", "file", "copy", "work/gamma.txt", "", "archive/gamma_copy.txt", "major", "Copy work/gamma.txt to archive/gamma_copy.txt."),
        AgentTask("LLMF04", "file", "create", "work/delta.txt", "delta seed", "", "major", "Create work/delta.txt with content delta seed."),
        AgentTask("LLMF05", "file", "delete", "work/obsolete.txt", "", "", "critical", "Delete work/obsolete.txt."),
        AgentTask("LLMF06", "file", "move", "work/alpha.txt", "", "archive/alpha.txt", "critical", "Move work/alpha.txt to archive/alpha.txt."),
        AgentTask("LLMF07", "file", "edit", "work/config.txt", "mode=production", "", "major", "Set work/config.txt to mode=production."),
        AgentTask("LLMF08", "file", "rename", "work/report_draft.md", "", "work/report_final.md", "critical", "Rename work/report_draft.md to work/report_final.md."),
        AgentTask("LLMF09", "file", "copy", "work/beta.txt", "", "work/beta_backup.txt", "major", "Copy work/beta.txt to work/beta_backup.txt."),
        AgentTask("LLMF10", "file", "delete", "work/temp.tmp", "", "", "critical", "Delete work/temp.tmp."),
        AgentTask("LLMW01", "web_form", "edit", "r1", "Alice", "", "critical", "Use the form to set record r1 name to Alice."),
        AgentTask("LLMW02", "web_form", "status", "r1", "closed", "", "major", "Use the form to set record r1 status to closed."),
        AgentTask("LLMW03", "web_form", "create", "new1", "Delta", "", "major", "Use the form to create record new1 with name Delta."),
        AgentTask("LLMW04", "web_form", "delete", "r2", "", "", "critical", "Use the form to delete record r2."),
        AgentTask("LLMW05", "web_form", "edit", "r3", "Gamma Prime", "", "critical", "Use the form to set record r3 name to Gamma Prime."),
        AgentTask("LLMW06", "web_form", "status", "r2", "archived", "", "major", "Use the form to set record r2 status to archived."),
        AgentTask("LLMW07", "web_form", "create", "new2", "Echo", "", "major", "Use the form to create record new2 with name Echo."),
        AgentTask("LLMW08", "web_form", "edit", "r1", "Aligned", "", "critical", "Use the form to set record r1 name to Aligned."),
        AgentTask("LLMW09", "web_form", "delete", "r3", "", "", "critical", "Use the form to delete record r3."),
        AgentTask("LLMW10", "web_form", "status", "r1", "approved", "", "major", "Use the form to set record r1 status to approved."),
    ]


def repair_context(task: AgentTask, before: Any, after: Any, expected: Any, error: str) -> str:
    return json.dumps(
        {
            "policy": "Repair the smallest local deviation needed to satisfy the original task.",
            "original_task": task.instruction,
            "before_state": before,
            "observed_state": after,
            "expected_state": expected,
            "execution_error": error,
        },
        sort_keys=True,
    )


def run_file_task(client: OpenAICompatibleClient, task: AgentTask, method: str, seed: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="csdvr_llm_file_") as d:
        root = Path(d)
        setup_files(root)
        backup = root / "_rollback"
        shutil.copytree(root / "work", backup / "work")
        shutil.copytree(root / "archive", backup / "archive")

        before = file_content_snapshot(root)
        expected = expected_file_snapshot(before, task)
        initial = ask_for_action(client, task, before)
        valid = initial.action is not None
        exec_ok = False
        exec_error = initial.error
        if initial.action is not None:
            exec_ok, exec_error = execute_file_action(root, initial.action)
        after_initial = file_content_snapshot(root)
        initial_fault = after_initial != expected
        detected = method != "NoCheck" and initial_fault
        repair_attempted = False
        rollback_used = False
        repair_calls = 0
        total_tokens = initial.tokens
        token_source = initial.token_source
        invalid_json = initial.invalid_json_count

        if detected and method in {"FinalVerifier", "C-SDVR"}:
            repair_attempted = True
            repair_calls += 1
            if method == "C-SDVR" and task.severity == "critical":
                rollback_used = True
                for child in list(root.iterdir()):
                    if child.name != "_rollback":
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                shutil.copytree(backup / "work", root / "work")
                shutil.copytree(backup / "archive", root / "archive")
            current = file_content_snapshot(root)
            repair = ask_for_action(client, task, current, repair_context(task, before, current, expected, exec_error))
            total_tokens += repair.tokens
            invalid_json += repair.invalid_json_count
            if repair.token_source == "estimated":
                token_source = "estimated"
            if repair.action is not None:
                execute_file_action(root, repair.action)

        final = file_content_snapshot(root)
        success = final == expected
        target_satisfied = success if task.op in {"rename", "move", "copy", "delete"} else final.get(task.target) == task.expected
        residue = not success and bool(target_satisfied)
        return make_row(
            seed,
            task,
            method,
            success,
            residue,
            target_satisfied,
            valid,
            exec_ok,
            initial_fault,
            detected,
            repair_attempted,
            rollback_used,
            repair_calls,
            invalid_json,
            total_tokens,
            token_source,
            h(final),
            exec_error,
        )


def run_form_task(client: OpenAICompatibleClient, browser, task: AgentTask, method: str, seed: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="csdvr_llm_form_") as d:
        db = Path(d) / "records.sqlite"
        server = ServerThread(db)
        base = server.start()
        page = None
        try:
            http_post(f"{base}/reset")
            page = browser.new_page()
            before = form_rows(base)
            expected = expected_form_rows(before, task)
            initial = ask_for_action(client, task, before)
            valid = initial.action is not None
            exec_ok = False
            exec_error = initial.error
            if initial.action is not None:
                exec_ok, exec_error = execute_form_action(page, base, initial.action)
            after_initial = form_rows(base)
            initial_fault = after_initial != expected
            detected = method != "NoCheck" and initial_fault
            repair_attempted = False
            rollback_used = False
            repair_calls = 0
            total_tokens = initial.tokens
            token_source = initial.token_source
            invalid_json = initial.invalid_json_count

            if detected and method in {"FinalVerifier", "C-SDVR"}:
                repair_attempted = True
                repair_calls += 1
                if method == "C-SDVR" and task.severity == "critical":
                    rollback_used = True
                    http_post(f"{base}/reset")
                current = form_rows(base)
                repair = ask_for_action(client, task, current, repair_context(task, before, current, expected, exec_error))
                total_tokens += repair.tokens
                invalid_json += repair.invalid_json_count
                if repair.token_source == "estimated":
                    token_source = "estimated"
                if repair.action is not None:
                    execute_form_action(page, base, repair.action)

            final = form_rows(base)
            success = final == expected
            target_satisfied = form_target_satisfied(final, task)
            residue = not success and target_satisfied
            return make_row(
                seed,
                task,
                method,
                success,
                residue,
                target_satisfied,
                valid,
                exec_ok,
                initial_fault,
                detected,
                repair_attempted,
                rollback_used,
                repair_calls,
                invalid_json,
                total_tokens,
                token_source,
                h(final),
                exec_error,
            )
        finally:
            if page is not None:
                page.close()
            server.stop()


def form_target_satisfied(rows: dict[str, dict[str, Any]], task: AgentTask) -> bool:
    if task.op == "create":
        return task.target in rows and rows[task.target]["name"] == task.expected
    if task.op == "edit":
        return task.target in rows and rows[task.target]["name"] == task.expected
    if task.op == "status":
        return task.target in rows and rows[task.target]["status"] == task.expected
    if task.op == "delete":
        return task.target not in rows
    return False


def make_row(
    seed: int,
    task: AgentTask,
    method: str,
    success: bool,
    residue: bool,
    target_satisfied: bool,
    action_valid: bool,
    exec_ok: bool,
    initial_fault: bool,
    detected: bool,
    repair_attempted: bool,
    rollback_used: bool,
    repair_calls: int,
    invalid_json: int,
    tokens: int,
    token_source: str,
    final_state_hash: str,
    error: str,
) -> dict[str, Any]:
    return {
        "seed": seed,
        "task_id": task.task_id,
        "domain": task.domain,
        "method": method,
        "severity": task.severity,
        "success": int(success),
        "residue": int(residue),
        "target_satisfied": int(target_satisfied),
        "initial_action_valid": int(action_valid),
        "initial_execution_ok": int(exec_ok),
        "initial_fault": int(initial_fault),
        "detected": int(detected),
        "repair_attempted": int(repair_attempted),
        "rollback_used": int(rollback_used),
        "unnecessary_repair": int(repair_attempted and not initial_fault),
        "repair_call_count": repair_calls,
        "invalid_json_count": invalid_json,
        "token_cost": tokens,
        "token_cost_source": token_source,
        "final_state_hash": final_state_hash,
        "error": error[:240],
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for method in METHODS:
        items = [r for r in rows if r["method"] == method]
        if not items:
            continue
        faulted = [r for r in items if int(r["initial_fault"])]
        nonfaulted = [r for r in items if not int(r["initial_fault"])]
        tp = sum(int(r["detected"]) for r in faulted)
        fn = len(faulted) - tp
        fp = sum(int(r["detected"]) for r in nonfaulted)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        critical_faults = [r for r in faulted if r["severity"] == "critical"]
        out.append(
            {
                "method": method,
                "n_runs": len(items),
                "success": f"{mean([int(r['success']) for r in items]):.4f}",
                "residue": f"{mean([int(r['residue']) for r in items]):.4f}",
                "detection_f1": f"{f1:.4f}",
                "critical_recall": f"{mean([int(r['detected']) for r in critical_faults]) if critical_faults else 0.0:.4f}",
                "rollback_use": f"{mean([int(r['rollback_used']) for r in items]):.4f}",
                "unnecessary_repair": f"{mean([int(r['unnecessary_repair']) for r in items]):.4f}",
                "repair_call_count": f"{mean([int(r['repair_call_count']) for r in items]):.4f}",
                "invalid_json_rate": f"{mean([1 if int(r['invalid_json_count']) else 0 for r in items]):.4f}",
                "token_cost": f"{mean([int(r['token_cost']) for r in items]):.2f}",
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write empty CSV")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write_report(path: Path, summary: list[dict[str, Any]], smoke: bool) -> None:
    lines = [
        "# LLM-Agent Validation Report",
        "",
        "Verification Status: VERIFIED WITH OPENAI-COMPATIBLE LLM ENDPOINT" if not smoke else "Verification Status: SMOKE TEST",
        "",
        "This validation uses real model calls to produce JSON actions for temporary filesystem tasks and Playwright-submitted local web-form tasks. It remains bounded to local reversible tasks and is not an open-world browser-agent evaluation.",
        "",
        "| Method | Runs | Success | Residue | Detection F1 | Critical recall | Rollback use | Repair calls | Invalid JSON rate | Token cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary:
        lines.append(
            f"| {r['method']} | {r['n_runs']} | {float(r['success']):.3f} | {float(r['residue']):.3f} | "
            f"{float(r['detection_f1']):.3f} | {float(r['critical_recall']):.3f} | "
            f"{float(r['rollback_use']):.3f} | {float(r['repair_call_count']):.3f} | "
            f"{float(r['invalid_json_rate']):.3f} | {float(r['token_cost']):.1f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_rows(rows: list[dict[str, Any]], smoke: bool) -> None:
    expected = 2 if smoke else 180
    if len(rows) != expected:
        raise AssertionError(f"expected {expected} rows, got {len(rows)}")
    required = {"task_id", "domain", "method", "success", "residue", "token_cost", "final_state_hash"}
    for idx, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            raise AssertionError(f"row {idx} missing {sorted(missing)}")
    if not smoke:
        by_method = {m: sum(1 for r in rows if r["method"] == m) for m in METHODS}
        if by_method != {"NoCheck": 60, "FinalVerifier": 60, "C-SDVR": 60}:
            raise AssertionError(f"unexpected method counts: {by_method}")


def run(smoke: bool, max_runs: int | None = None) -> None:
    base_url, model, api_key = require_env()
    client = OpenAICompatibleClient(base_url, model, api_key)
    tasks = [all_tasks()[0], all_tasks()[10]] if smoke else all_tasks()
    methods = ["C-SDVR"] if smoke else METHODS
    seeds = [0] if smoke else [0, 1, 2]
    raw_path, summary_path, report_path = (SMOKE_RAW, SMOKE_SUMMARY, SMOKE_REPORT) if smoke else (RAW, SUMMARY, REPORT)

    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    plan = [(seed, task, method) for seed in seeds for task in tasks for method in methods]
    if max_runs is not None:
        plan = plan[:max_runs]
    total = len(plan)
    print(
        f"Starting LLM-agent validation: runs={total}, model={model}, base_url={base_url}, "
        f"timeout={os.getenv('CSDVR_LLM_TIMEOUT', '90')}s",
        flush=True,
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for idx, (seed, task, method) in enumerate(plan, start=1):
                started = time.time()
                print(
                    f"[{idx}/{total}] start seed={seed} task={task.task_id} "
                    f"domain={task.domain} method={method}",
                    flush=True,
                )
                if task.domain == "file":
                    row = run_file_task(client, task, method, seed)
                else:
                    row = run_form_task(client, browser, task, method, seed)
                rows.append(row)
                print(
                    f"[{idx}/{total}] done success={row['success']} residue={row['residue']} "
                    f"detected={row['detected']} repair={row['repair_attempted']} "
                    f"tokens={row['token_cost']} elapsed={time.time() - started:.1f}s",
                    flush=True,
                )
        finally:
            browser.close()

    if max_runs is None:
        validate_rows(rows, smoke)
    write_csv(raw_path, rows)
    summary = summarize(rows)
    write_csv(summary_path, summary)
    write_report(report_path, summary, smoke)
    print(f"llm_agent_runs={len(rows)}")
    print(report_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded LLM-agent validation for C-SDVR.")
    parser.add_argument("--smoke", action="store_true", help="Run 2 tasks x 1 method x 1 repetition.")
    parser.add_argument("--max-runs", type=int, default=None, help="Debug only: stop after N planned runs.")
    args = parser.parse_args()
    run(args.smoke, args.max_runs)


if __name__ == "__main__":
    main()
