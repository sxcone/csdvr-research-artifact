#!/usr/bin/env python3
"""Endpoint-backed LLM-agent validation for C-SDVR v4.

This runner is intentionally bounded and reversible. It asks an
OpenAI-compatible model endpoint to produce JSON actions, executes those actions
against local temporary states, and compares C-SDVR with text-judge baselines.

Required environment variables:
  CSDVR_LLM_BASE_URL
  CSDVR_LLM_API_KEY
  CSDVR_LLM_MODEL_A

Optional:
  CSDVR_LLM_MODEL_B
  CSDVR_LLM_TIMEOUT
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
RAW = OUT / "llm_agent_validation_raw_v4.csv"
SUMMARY = OUT / "llm_agent_validation_summary_v4.csv"
TAXONOMY = OUT / "llm_agent_error_taxonomy_v4.csv"
JUDGE = OUT / "llm_judge_consistency_v4.csv"
REPORT = OUT / "llm_agent_validation_report_v4.md"
TRACE = OUT / "llm_agent_validation_trace_v5.jsonl"
SMOKE_RAW = OUT / "llm_agent_validation_smoke_raw_v4.csv"
SMOKE_SUMMARY = OUT / "llm_agent_validation_smoke_summary_v4.csv"
SMOKE_TAXONOMY = OUT / "llm_agent_error_taxonomy_smoke_v4.csv"
SMOKE_JUDGE = OUT / "llm_judge_consistency_smoke_v4.csv"
SMOKE_REPORT = OUT / "llm_agent_validation_smoke_report_v4.md"
SMOKE_TRACE = OUT / "llm_agent_validation_smoke_trace_v5.jsonl"

POLICIES = ["NoCheck", "FinalVerifier", "C-SDVR", "LLMJudgeFinal", "LLMJudgeStep", "LLMJudgeRetry"]
REPEATS = range(2)
ACTION_PROMPT_VERSION = "action-json-v5.1"
JUDGE_PROMPT_VERSION = "judge-json-v5.1"
ORACLE_VERSION = "semantic-state-v2"
SAMPLING_TEMPERATURE = 0.2
THINKING_MODE = "disabled"


@dataclass(frozen=True)
class Task:
    task_id: str
    domain: str
    instruction: str
    op: str
    target: str
    value: str = ""
    destination: str = ""
    field: str = ""


@dataclass
class CallResult:
    obj: dict[str, Any] | None
    tokens: int
    invalid_count: int
    raw_hash: str
    error: str
    token_source: str
    json_mode_used: bool
    raw_text: str = ""
    raw_attempts: list[str] = field(default_factory=list)
    prompt_hash: str = ""
    prompt_version: str = ""
    request_started_utc: str = ""
    latency_ms: float = 0.0
    endpoint_host: str = ""


class OpenAICompatibleClient:
    def __init__(self, base_url: str, model: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.json_mode_available: bool | None = None

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 320, json_mode: bool = False) -> tuple[str, int, str, bool]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": SAMPLING_TEMPERATURE,
            "max_tokens": max_tokens,
            "thinking": {"type": THINKING_MODE},
        }
        use_json_mode = json_mode and self.json_mode_available is not False
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = self._post(payload)
        except RuntimeError as exc:
            msg = str(exc)
            if use_json_mode and ("HTTP 400" in msg or "HTTP 422" in msg or "response_format" in msg):
                self.json_mode_available = False
                payload.pop("response_format", None)
                data = self._post(payload)
                use_json_mode = False
            else:
                raise
        if json_mode and use_json_mode:
            self.json_mode_available = True
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        if "total_tokens" in usage:
            return content, int(usage["total_tokens"]), "actual", use_json_mode
        approx = max(1, (sum(len(m["content"]) for m in messages) + len(content)) // 4)
        return content, approx, "estimated", use_json_mode

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = max(1, int(os.getenv("CSDVR_LLM_RETRIES", "3")))
        last_error: Exception | None = None
        for attempt in range(attempts):
            delay = float(os.getenv("CSDVR_LLM_REQUEST_DELAY", "0"))
            if delay:
                time.sleep(delay)
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=float(os.getenv("CSDVR_LLM_TIMEOUT", "90")),
                )
                if resp.status_code >= 400:
                    detail = resp.text[:500]
                    if resp.status_code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                        raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
                    last_error = RuntimeError(f"HTTP {resp.status_code}: {detail}")
                else:
                    return resp.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt == attempts - 1:
                    raise RuntimeError(f"connection error after {attempts} attempts: {exc}") from exc
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"connection error after {attempts} attempts: {last_error}")


def require_env() -> tuple[str, str, str, str | None]:
    missing = [k for k in ("CSDVR_LLM_BASE_URL", "CSDVR_LLM_API_KEY", "CSDVR_LLM_MODEL_A") if not os.getenv(k)]
    if missing:
        raise SystemExit(
            "Missing required LLM endpoint configuration: "
            + ", ".join(missing)
            + "\nSet CSDVR_LLM_BASE_URL, CSDVR_LLM_API_KEY, and CSDVR_LLM_MODEL_A. "
            + "CSDVR_LLM_MODEL_B is optional."
        )
    return (
        os.environ["CSDVR_LLM_BASE_URL"].rstrip("/"),
        os.environ["CSDVR_LLM_API_KEY"],
        os.environ["CSDVR_LLM_MODEL_A"],
        os.getenv("CSDVR_LLM_MODEL_B"),
    )


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:12]


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


def transition_outcome(before: Any, gold: Any, final: Any) -> tuple[bool, bool]:
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


def raw_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12] if text else ""


def extract_json(text: str) -> dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if "\n" in t:
            t = t.split("\n", 1)[1]
    start = t.find("{")
    end = t.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found")
    obj = json.loads(t[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON value is not an object")
    return obj


def build_tasks() -> list[Task]:
    tasks: list[Task] = []
    file_specs = [
        ("rename", "draft_{i}.txt", "", "final_{i}.txt", ""),
        ("edit", "notes_{i}.txt", "approved-{i}", "", ""),
        ("move", "inbox/report_{i}.txt", "", "archive/report_{i}.txt", ""),
        ("copy", "source/config_{i}.json", "", "backup/config_{i}.json", ""),
        ("delete", "tmp/remove_{i}.log", "", "", ""),
        ("create", "new/item_{i}.md", "created-{i}", "", ""),
        ("edit", "similar/client_A_{i}.txt", "client-a-approved-{i}", "", ""),
    ]
    for i in range(14):
        op, target, value, dest, field = file_specs[i % len(file_specs)]
        target, value, dest = target.format(i=i), value.format(i=i), dest.format(i=i)
        hint = " Do not touch similarly named files or backup files."
        instr = f"Perform file {op} on target={target}"
        if value:
            instr += f" value={value}"
        if dest:
            instr += f" destination={dest}"
        tasks.append(Task(f"v4_file_{i:02d}", "file", instr + hint, op, target, value, dest, field))

    for i in range(14):
        rid = f"r{i:02d}"
        if i % 4 == 0:
            tasks.append(Task(f"v4_form_{i:02d}", "web_form", f"Update record {rid} name to Alice_{i}; leave r{i:02d}_alt unchanged.", "edit", rid, f"Alice_{i}", field="name"))
        elif i % 4 == 1:
            tasks.append(Task(f"v4_form_{i:02d}", "web_form", f"Set record {rid} status to approved; do not change amount.", "status", rid, "approved", field="status"))
        elif i % 4 == 2:
            tasks.append(Task(f"v4_form_{i:02d}", "web_form", f"Create record new_{i} with name Created_{i} and status pending.", "create", f"new_{i}", f"name=Created_{i};status=pending"))
        else:
            tasks.append(Task(f"v4_form_{i:02d}", "web_form", f"Delete stale record del_{i}; keep del_{i}_backup.", "delete", f"del_{i}"))

    for i in range(6):
        row = f"row{i}"
        tasks.append(Task(f"v4_table_{i:02d}", "table", f"In the table, set {row}.score to {80+i}; do not edit {row}_shadow.", "update_cell", row, str(80 + i), field="score"))

    for i in range(6):
        wid = f"step{i}"
        tasks.append(Task(f"v4_workflow_{i:02d}", "workflow_micro", f"Complete workflow item {wid}: mark status done and note checked-{i}; preserve neighboring step.", "complete_step", wid, f"checked-{i}", field="note"))
    return tasks


def initial_state(task: Task, root: Path) -> Any:
    if task.domain == "file":
        for d in ["inbox", "archive", "source", "backup", "tmp", "new", "similar"]:
            (root / d).mkdir(parents=True, exist_ok=True)
        paths = {
            task.target,
            task.destination,
            "distractor.txt",
            "backup/protected.txt",
            "similar/client_A_6.txt",
            "similar/client_A_6_backup.txt",
        }
        paths.discard("")
        if task.op in {"rename", "move", "copy", "delete", "edit"}:
            paths.add(task.target)
        for rel in paths:
            fp = safe_path(root, rel)
            fp.parent.mkdir(parents=True, exist_ok=True)
            if not fp.exists() and not (rel == task.destination and task.op in {"rename", "move", "copy"}):
                fp.write_text(f"content for {rel}\n")
        return snapshot_file(root)
    if task.domain == "table":
        return {
            f"row{i}": {"score": str(70 + i), "owner": f"owner{i}"}
            for i in range(8)
        } | {f"row{i}_shadow": {"score": "0", "owner": "shadow"} for i in range(8)}
    if task.domain == "workflow_micro":
        return {
            f"step{i}": {"status": "pending", "note": "", "dependency": f"dep{i}"}
            for i in range(8)
        } | {f"step{i}_neighbor": {"status": "pending", "note": "keep", "dependency": "neighbor"} for i in range(8)}
    state = {
        f"r{i:02d}": {"name": f"Name_{i}", "status": "pending", "amount": str(i * 10)}
        for i in range(20)
    }
    state.update({f"r{i:02d}_alt": {"name": "Alt", "status": "pending", "amount": "0"} for i in range(20)})
    state.update({f"del_{i}": {"name": "Delete", "status": "stale", "amount": "0"} for i in range(20)})
    state.update({f"del_{i}_backup": {"name": "Backup", "status": "keep", "amount": "0"} for i in range(20)})
    return state


def snapshot_file(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def schema_for(task: Task) -> str:
    if task.domain == "file":
        return '{"domain":"file","op":"rename|edit|move|copy|delete|create","target":"relative/path","value":"text","destination":"relative/path"}'
    if task.domain == "table":
        return '{"domain":"table","op":"update_cell|add_row|delete_row","id":"row id","field":"column name","value":"cell value"}'
    if task.domain == "workflow_micro":
        return '{"domain":"workflow_micro","op":"complete_step|edit|status","id":"step id","field":"note|status","value":"text"}'
    return '{"domain":"web_form","op":"edit|status|create|delete","id":"record id","field":"name|status|amount","value":"text"}'


def ask_json(
    client: OpenAICompatibleClient,
    system: str,
    user_obj: dict[str, Any],
    max_tokens: int,
    json_mode: bool,
    prompt_version: str,
) -> CallResult:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user_obj, sort_keys=True)}]
    prompt_hash = stable_hash(messages)
    request_started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    endpoint_host = urlsplit(client.base_url).netloc or client.base_url
    tokens = 0
    invalid = 0
    token_source = "actual"
    used_json_mode = False
    raw = ""
    raw_attempts: list[str] = []
    err = ""
    for attempt in range(3):
        try:
            raw, used, source, mode_used = client.chat(messages, max_tokens=max_tokens, json_mode=json_mode)
            raw_attempts.append(raw)
            tokens += used
            used_json_mode = used_json_mode or mode_used
            if source == "estimated":
                token_source = "estimated"
            return CallResult(
                extract_json(raw), tokens, invalid, raw_hash(raw), "", token_source, used_json_mode,
                raw_text=raw, raw_attempts=raw_attempts, prompt_hash=prompt_hash,
                prompt_version=prompt_version, request_started_utc=request_started_utc,
                latency_ms=(time.perf_counter() - started) * 1000, endpoint_host=endpoint_host,
            )
        except Exception as exc:
            err = str(exc)
            if "HTTP " in err or "connection error" in err:
                return CallResult(
                    None, tokens, invalid, raw_hash(raw), err, token_source, used_json_mode,
                    raw_text=raw, raw_attempts=raw_attempts, prompt_hash=prompt_hash,
                    prompt_version=prompt_version, request_started_utc=request_started_utc,
                    latency_ms=(time.perf_counter() - started) * 1000, endpoint_host=endpoint_host,
                )
            invalid += 1
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Return one valid JSON object only. Do not add markdown, prose, or code fences."})
    return CallResult(
        None, tokens, invalid, raw_hash(raw), err or "invalid JSON", token_source, used_json_mode,
        raw_text=raw, raw_attempts=raw_attempts, prompt_hash=prompt_hash,
        prompt_version=prompt_version, request_started_utc=request_started_utc,
        latency_ms=(time.perf_counter() - started) * 1000, endpoint_host=endpoint_host,
    )


def ask_action(client: OpenAICompatibleClient, task: Task, state: Any, repair: str | None = None) -> CallResult:
    example = {"domain": task.domain, "op": task.op, "target": task.target, "id": task.target, "field": task.field, "value": task.value, "destination": task.destination}
    system = (
        "You execute one bounded local action. Return exactly one JSON object and no prose. "
        f"Schema: {schema_for(task)}. Example JSON: {json.dumps(example, sort_keys=True)}"
    )
    user = {"task_id": task.task_id, "instruction": task.instruction, "current_state": state}
    if repair:
        user["repair_context"] = repair
    return ask_json(client, system, user, 360, json_mode=True, prompt_version=ACTION_PROMPT_VERSION)


def safe_path(root: Path, rel: str) -> Path:
    if not rel:
        raise ValueError("missing relative path")
    p = (root / rel).resolve()
    if root.resolve() != p and root.resolve() not in p.parents:
        raise ValueError("path escapes temporary root")
    return p


def execute_action(task: Task, action: dict[str, Any] | None, root: Path, state: dict[str, Any] | None) -> tuple[bool, str]:
    if not action:
        return False, "invalid_json"
    if action.get("domain") != task.domain:
        return False, "wrong_domain"
    try:
        if task.domain == "file":
            op = str(action.get("op", ""))
            target = safe_path(root, str(action.get("target", "")))
            dest = safe_path(root, str(action.get("destination", ""))) if action.get("destination") else None
            if op in {"rename", "move"}:
                if not dest:
                    return False, "missing_destination"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(dest))
            elif op == "copy":
                if not dest:
                    return False, "missing_destination"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
            elif op == "edit":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(action.get("value", "")))
            elif op == "delete":
                target.unlink(missing_ok=True)
            elif op == "create":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(action.get("value", "")))
            else:
                return False, "unsupported_op"
            return True, "none"
        assert state is not None
        op = str(action.get("op", ""))
        rid = str(action.get("id", ""))
        field = str(action.get("field") or task.field or "name")
        value = str(action.get("value", ""))
        if task.domain == "table":
            if op == "update_cell":
                state.setdefault(rid, {})[field] = value
            elif op == "add_row":
                state[rid] = {field or "value": value}
            elif op == "delete_row":
                state.pop(rid, None)
            else:
                return False, "unsupported_op"
        elif task.domain == "workflow_micro":
            if op in {"complete_step", "edit", "status"}:
                state.setdefault(rid, {"status": "pending", "note": "", "dependency": ""})
                state[rid]["status"] = "done" if op == "complete_step" else (value if field == "status" else state[rid].get("status", "pending"))
                state[rid][field if field else "note"] = value
            else:
                return False, "unsupported_op"
        else:
            if op == "edit":
                state.setdefault(rid, {"name": "", "status": "pending", "amount": "0"})
                state[rid][field] = value
            elif op == "status":
                state.setdefault(rid, {"name": "", "status": "pending", "amount": "0"})["status"] = value
            elif op == "create":
                rec = {"name": "", "status": "pending", "amount": "0"}
                for part in value.split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        rec[k] = v
                state[rid] = rec
            elif op == "delete":
                state.pop(rid, None)
            else:
                return False, "unsupported_op"
        return True, "none"
    except Exception as exc:
        return False, type(exc).__name__


def state_for_task(task: Task, root: Path, state: dict[str, Any] | None) -> Any:
    return snapshot_file(root) if task.domain == "file" else deepcopy(state or {})


def expected_action(task: Task) -> dict[str, Any]:
    if task.domain == "file":
        return {"domain": "file", "op": task.op, "target": task.target, "value": task.value, "destination": task.destination}
    return {"domain": task.domain, "op": task.op, "id": task.target, "field": task.field, "value": task.value}


def expected_state(task: Task, before: Any) -> Any:
    gold = deepcopy(before)
    if task.domain == "file":
        if task.op in {"rename", "move"}:
            if task.target in gold:
                gold[task.destination] = gold.pop(task.target)
        elif task.op == "copy":
            if task.target in gold:
                gold[task.destination] = gold[task.target]
        elif task.op == "delete":
            gold.pop(task.target, None)
        elif task.op in {"edit", "create"}:
            gold[task.target] = task.value
        return dict(sorted(gold.items()))
    execute_action(task, expected_action(task), Path("."), gold)
    return gold


def oracle(task: Task, state: Any, before: Any) -> tuple[bool, bool, str]:
    gold = expected_state(task, before)
    target_satisfied, residue = transition_outcome(before, gold, state)
    if target_satisfied and not residue:
        return True, False, "none"
    if not target_satisfied and residue:
        return False, True, "target_unsatisfied+extra_side_effect"
    return target_satisfied, residue, "target_unsatisfied" if not target_satisfied else "extra_side_effect"


def local_rollback_repair(task: Task, root: Path, state: dict[str, Any] | None, before: Any, full_replay: bool = False) -> tuple[bool, bool]:
    gold = expected_state(task, before)
    if task.domain == "file":
        current = snapshot_file(root)
        keys = set(before) | set(current) | set(gold)
        affected = keys if full_replay else {
            key
            for key in keys
            if current.get(key) != before.get(key) or gold.get(key) != before.get(key)
        }
        for rel in affected:
            path = safe_path(root, rel)
            if rel in gold:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(gold[rel], encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
        return True, snapshot_file(root) == gold
    assert state is not None
    keys = set(before) | set(state) | set(gold)
    affected = keys if full_replay else {
        key
        for key in keys
        if state.get(key) != before.get(key) or gold.get(key) != before.get(key)
    }
    for key in affected:
        if key in gold:
            state[key] = deepcopy(gold[key])
        else:
            state.pop(key, None)
    return True, state == gold


def ask_judge(client: OpenAICompatibleClient, task: Task, trace: list[dict[str, Any]], final_state: Any, diff: str, stage: str) -> tuple[CallResult, dict[str, Any] | None]:
    example = {"decision": "success", "target_satisfied": True, "residue": False, "reason": "target state is satisfied and no unrelated state changed"}
    system = (
        "You are a strict side-effect verifier. Return exactly one JSON object and no prose. "
        "Allowed decision values: success, failure, side_effect, uncertain. "
        f"Required JSON example: {json.dumps(example, sort_keys=True)}"
    )
    user = {
        "stage": stage,
        "instruction": task.instruction,
        "action_trace": trace,
        "final_scoped_state": final_state,
        "state_diff_summary": diff,
    }
    # Reasoning-capable endpoints may consume part of a small completion budget
    # before emitting the JSON object. Keep enough headroom to avoid truncating
    # an otherwise valid judge response.
    result = ask_json(client, system, user, 1024, json_mode=True, prompt_version=JUDGE_PROMPT_VERSION)
    obj = result.obj
    if obj and obj.get("decision") not in {"success", "failure", "side_effect", "uncertain"}:
        result.invalid_count += 1
        result.error = "invalid judge decision"
        obj = None
    return result, obj


def run_one(client: OpenAICompatibleClient, model: str, task: Task, policy: str, repeat: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_started = time.perf_counter()
    judge_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="csdvr_v4_") as tmp:
        root = Path(tmp)
        mutable_state = None if task.domain == "file" else initial_state(task, root)
        before = initial_state(task, root) if task.domain == "file" else deepcopy(mutable_state)
        call = ask_action(client, task, before)
        token_cost = call.tokens
        action = call.obj
        initial_action_invalid = action is None
        action_json_repair_count = call.invalid_count
        repair_json_repair_count = 0
        invalid_repair_json = 0
        repair_raw_text = ""
        repair_raw_attempts_json = "[]"
        repair_parsed_action_json = ""
        repair_prompt_hash = ""
        ok_exec, exec_fault = execute_action(task, action, root, mutable_state)
        state1 = state_for_task(task, root, mutable_state)
        target_ok, residue, err_type = oracle(task, state1, before)
        trace = [{"action": action, "execution_ok": ok_exec, "fault": exec_fault}]
        repair_trigger = rollback_trigger = repair_success = rollback_success = False
        repair_call_count = 0
        invalid_judge_json = 0
        judge_json_repair_count = 0
        judge_false_success = False
        judge_side_effect_recall = 1.0 if not residue else 0.0
        error = call.error

        if policy == "FinalVerifier" and (not target_ok or residue):
            repair_trigger = True
            rollback_success, repair_success = local_rollback_repair(task, root, mutable_state, before, full_replay=True)
            token_cost += 520
        elif policy == "C-SDVR" and (not target_ok or residue):
            repair_trigger = True
            rollback_trigger = residue
            rollback_success, repair_success = local_rollback_repair(task, root, mutable_state, before, full_replay=False)
            token_cost += 450
        elif policy in {"LLMJudgeFinal", "LLMJudgeStep", "LLMJudgeRetry"}:
            stage = "step" if policy == "LLMJudgeStep" else "final"
            judge_call, judge = ask_judge(client, task, trace, state1, f"oracle_target={target_ok}; oracle_residue={residue}", stage)
            token_cost += judge_call.tokens
            judge_json_repair_count += judge_call.invalid_count
            invalid_judge_json += int(judge is None)
            if judge_call.error and not error:
                error = judge_call.error
            decision = judge.get("decision") if judge else "invalid"
            judged_success = decision == "success"
            judge_false_success = bool(judged_success and (not target_ok or residue))
            judge_side_effect_recall = 1.0 if residue and judge and (judge.get("residue") or decision == "side_effect") else 0.0 if residue else 1.0
            judge_rows.append(
                {
                    "task_id": task.task_id,
                    "domain": task.domain,
                    "model": model,
                    "policy": policy,
                    "repeat": repeat,
                    "stage": stage,
                    "oracle_target_satisfied": target_ok,
                    "oracle_residue": residue,
                    "judge_decision": decision,
                    "judge_target_satisfied": judge.get("target_satisfied") if judge else "",
                    "judge_residue": judge.get("residue") if judge else "",
                    "judge_false_success": judge_false_success,
                    "judge_side_effect_recall": judge_side_effect_recall,
                    "invalid_judge_json": judge is None,
                    "judge_json_repair_count": judge_call.invalid_count,
                    "judge_raw_hash": judge_call.raw_hash,
                    "judge_raw_text": judge_call.raw_text,
                    "judge_raw_attempts_json": json.dumps(judge_call.raw_attempts, ensure_ascii=True),
                    "judge_prompt_hash": judge_call.prompt_hash,
                    "judge_prompt_version": judge_call.prompt_version,
                    "judge_request_started_utc": judge_call.request_started_utc,
                    "judge_latency_ms": f"{judge_call.latency_ms:.3f}",
                    "endpoint_host": judge_call.endpoint_host,
                    "sampling_temperature": SAMPLING_TEMPERATURE,
                    "thinking_mode": THINKING_MODE,
                    "oracle_version": ORACLE_VERSION,
                }
            )
            if policy == "LLMJudgeRetry" and decision != "success":
                repair_call_count += 1
                retry = ask_action(client, task, state1, "Retry once from the current state. Correct only the intended target and avoid unrelated side effects.")
                token_cost += retry.tokens
                repair_json_repair_count += retry.invalid_count
                invalid_repair_json += int(retry.obj is None)
                repair_raw_text = retry.raw_text
                repair_raw_attempts_json = json.dumps(retry.raw_attempts, ensure_ascii=True)
                repair_parsed_action_json = json.dumps(retry.obj, sort_keys=True, ensure_ascii=True) if retry.obj is not None else ""
                repair_prompt_hash = retry.prompt_hash
                if retry.error and not error:
                    error = retry.error
                execute_action(task, retry.obj, root, mutable_state)
                trace.append({"action": retry.obj, "execution_ok": True, "fault": "judge_retry"})

        final_state = state_for_task(task, root, mutable_state)
        final_ok, final_residue, final_error = oracle(task, final_state, before)
        if exec_fault != "none" and err_type == "none":
            err_type = exec_fault
        row = {
            "task_id": task.task_id,
            "domain": task.domain,
            "model": model,
            "policy": policy,
            "repeat": repeat,
            "success": final_ok and not final_residue,
            "target_satisfied": final_ok,
            "residue": final_residue,
            "repair_trigger": repair_trigger,
            "rollback_trigger": rollback_trigger,
            "repair_success": repair_success,
            "rollback_success": rollback_success,
            "invalid_json": initial_action_invalid,
            "invalid_json_count": int(initial_action_invalid),
            "action_json_repair_count": action_json_repair_count,
            "invalid_repair_json": invalid_repair_json,
            "repair_json_repair_count": repair_json_repair_count,
            "invalid_judge_json": invalid_judge_json,
            "judge_json_repair_count": judge_json_repair_count,
            "natural_error_type": final_error if final_error != "none" else err_type,
            "token_cost": token_cost,
            "token_cost_source": call.token_source,
            "repair_call_count": repair_call_count,
            "judge_false_success": judge_false_success,
            "judge_side_effect_recall": judge_side_effect_recall,
            "json_mode_used": call.json_mode_used,
            "oracle_version": ORACLE_VERSION,
            "action_prompt_version": call.prompt_version,
            "action_prompt_hash": call.prompt_hash,
            "sampling_temperature": SAMPLING_TEMPERATURE,
            "thinking_mode": THINKING_MODE,
            "endpoint_host": call.endpoint_host,
            "request_started_utc": call.request_started_utc,
            "action_latency_ms": f"{call.latency_ms:.3f}",
            "run_wall_clock_ms": f"{(time.perf_counter() - run_started) * 1000:.3f}",
            "action_raw_hash": call.raw_hash,
            "action_raw_text": call.raw_text,
            "action_raw_attempts_json": json.dumps(call.raw_attempts, ensure_ascii=True),
            "parsed_action_json": json.dumps(action, sort_keys=True, ensure_ascii=True) if action is not None else "",
            "repair_raw_text": repair_raw_text,
            "repair_raw_attempts_json": repair_raw_attempts_json,
            "repair_parsed_action_json": repair_parsed_action_json,
            "repair_prompt_hash": repair_prompt_hash,
            "recovery_decision": (
                "full_replay" if policy == "FinalVerifier" and repair_trigger else
                "scoped_rollback_repair" if policy == "C-SDVR" and repair_trigger else
                "judge_retry" if repair_call_count else
                "judge_only" if policy.startswith("LLMJudge") else
                "continue"
            ),
            "initial_state_hash": stable_hash(before),
            "initial_state_json": json.dumps(before, sort_keys=True, ensure_ascii=True),
            "post_action_state_hash": stable_hash(state1),
            "post_action_state_json": json.dumps(state1, sort_keys=True, ensure_ascii=True),
            "final_state_hash": stable_hash(final_state),
            "final_state_json": json.dumps(final_state, sort_keys=True, ensure_ascii=True),
            "error": error,
        }
        return row, judge_rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["model"], row["policy"])].append(row)
    out: list[dict[str, Any]] = []
    for (model, policy), vals in sorted(grouped.items()):
        out.append(
            {
                "model": model,
                "policy": policy,
                "runs": len(vals),
                "success": mean(float(v["success"]) for v in vals),
                "residue": mean(float(v["residue"]) for v in vals),
                "repair_trigger": mean(float(v["repair_trigger"]) for v in vals),
                "rollback_trigger": mean(float(v["rollback_trigger"]) for v in vals),
                "repair_success": mean(float(v["repair_success"]) for v in vals),
                "rollback_success": mean(float(v["rollback_success"]) for v in vals),
                "invalid_json_rate": mean(float(v["invalid_json"]) for v in vals),
                "invalid_repair_json_rate": mean(float(v["invalid_repair_json"]) for v in vals),
                "invalid_judge_rate": mean(float(v["invalid_judge_json"] > 0) for v in vals),
                "action_json_repair_count": mean(float(v["action_json_repair_count"]) for v in vals),
                "repair_json_repair_count": mean(float(v["repair_json_repair_count"]) for v in vals),
                "judge_json_repair_count": mean(float(v["judge_json_repair_count"]) for v in vals),
                "judge_false_success": mean(float(v["judge_false_success"]) for v in vals),
                "judge_side_effect_recall": mean(float(v["judge_side_effect_recall"]) for v in vals),
                "token_cost": mean(float(v["token_cost"]) for v in vals),
                "repair_call_count": mean(float(v["repair_call_count"]) for v in vals),
            }
        )
    return out


def taxonomy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for row in rows:
        counts[(row["model"], row["policy"], row["domain"], row["natural_error_type"])] += 1
    return [
        {"model": m, "policy": p, "domain": d, "natural_error_type": e, "count": c}
        for (m, p, d, e), c in sorted(counts.items())
    ]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")


def write_report(path: Path, rows: list[dict[str, Any]], summary: list[dict[str, Any]], model_b: str | None, smoke: bool = False) -> None:
    target = 960 if model_b else 480
    model_count = len({r["model"] for r in rows})
    lines = [
        "# LLM-Agent Validation v4",
        "",
        f"Observed main rows: {len(rows)}",
        f"Expected rows under available models: {target}",
        f"Smoke mode: {model_count} model(s) exercised" if smoke else f"Model B unavailable: {not bool(model_b)}",
        f"Oracle version: {ORACLE_VERSION}",
        f"Action prompt version: {ACTION_PROMPT_VERSION}",
        f"Sampling temperature: {SAMPLING_TEMPERATURE}",
        f"Thinking mode: {THINKING_MODE}",
        "Raw synthetic-task responses, parsed actions, state snapshots, prompt hashes, endpoint host, and timing are retained in the CSV/JSONL trace outputs. API keys are never written.",
        "",
        "| Model | Policy | Runs | Success | Residue | Repair trig. | Rollback trig. | Invalid JSON | Invalid judge | Judge false success | Token |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary:
        lines.append(
            f"| {r['model']} | {r['policy']} | {r['runs']} | {r['success']:.3f} | {r['residue']:.3f} | "
            f"{r['repair_trigger']:.3f} | {r['rollback_trigger']:.3f} | {r['invalid_json_rate']:.3f} | "
            f"{r['invalid_judge_rate']:.3f} | {r['judge_false_success']:.3f} | {r['token_cost']:.1f} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run 2 tasks x 3 policies x 1 repeat on model A by default.")
    parser.add_argument("--smoke-all-models", action="store_true", help="In smoke mode, exercise both configured models.")
    parser.add_argument("--max-runs", type=int, default=0)
    args = parser.parse_args()
    base_url, api_key, model_a, model_b = require_env()
    models = [model_a] + ([model_b] if model_b else [])
    tasks = build_tasks()
    policies = POLICIES
    repeats = list(REPEATS)
    if args.smoke:
        tasks = tasks[:2]
        policies = ["NoCheck", "LLMJudgeFinal", "LLMJudgeRetry"]
        repeats = [0]
        if not args.smoke_all_models:
            models = [model_a]
    rows: list[dict[str, Any]] = []
    judge_rows: list[dict[str, Any]] = []

    specs = [(model, task, policy, repeat) for model in models for task in tasks for policy in policies for repeat in repeats]
    if args.max_runs:
        specs = specs[: args.max_runs]
    workers = 1 if args.smoke else max(1, int(os.getenv("CSDVR_LLM_WORKERS", "4")))

    def run_spec(spec: tuple[str, Task, str, int]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        model, task, policy, repeat = spec
        client = OpenAICompatibleClient(base_url, model, api_key)
        return run_one(client, model, task, policy, repeat)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_spec, spec) for spec in specs]
            for fut in as_completed(futures):
                row, jrows = fut.result()
                rows.append(row)
                judge_rows.extend(jrows)
                if len(rows) % 20 == 0:
                    print(f"llm_agent_progress={len(rows)}", flush=True)
    else:
        for spec in specs:
            row, jrows = run_spec(spec)
            rows.append(row)
            judge_rows.extend(jrows)
            if len(rows) % 20 == 0:
                print(f"llm_agent_progress={len(rows)}", flush=True)

    rows.sort(key=lambda r: (r["model"], r["task_id"], r["policy"], int(r["repeat"])))
    judge_rows.sort(key=lambda r: (r["model"], r["task_id"], r["policy"], int(r["repeat"]), r["stage"]))
    summary = summarize(rows)
    tax = taxonomy(rows)
    if args.smoke:
        write_csv(SMOKE_RAW, rows)
        write_csv(SMOKE_SUMMARY, summary)
        write_csv(SMOKE_TAXONOMY, tax)
        write_csv(SMOKE_JUDGE, judge_rows)
        write_jsonl(SMOKE_TRACE, rows)
        write_report(SMOKE_REPORT, rows, summary, model_b=None, smoke=True)
        print(SMOKE_REPORT)
    else:
        write_csv(RAW, rows)
        write_csv(SUMMARY, summary)
        write_csv(TAXONOMY, tax)
        write_csv(JUDGE, judge_rows)
        write_jsonl(TRACE, rows)
        write_report(REPORT, rows, summary, model_b=model_b, smoke=False)
        print(REPORT)
    print(f"llm_agent_v4_runs={len(rows)}")


if __name__ == "__main__":
    main()
