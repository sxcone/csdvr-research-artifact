#!/usr/bin/env python3
"""Endpoint-backed LLM-generated postcondition study for C-SDVR v4."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
RAW = OUT / "postcondition_generation_raw_v4.csv"
SUMMARY = OUT / "postcondition_generation_summary_v4.csv"
ERRORS = OUT / "postcondition_error_taxonomy_v4.csv"
DOWNSTREAM = OUT / "postcondition_downstream_v4.csv"
REPORT = OUT / "postcondition_generation_report_v4.md"
SMOKE_RAW = OUT / "postcondition_generation_smoke_raw_v4.csv"
SMOKE_SUMMARY = OUT / "postcondition_generation_smoke_summary_v4.csv"
SMOKE_ERRORS = OUT / "postcondition_error_taxonomy_smoke_v4.csv"
SMOKE_DOWNSTREAM = OUT / "postcondition_downstream_smoke_v4.csv"
SMOKE_REPORT = OUT / "postcondition_generation_smoke_report_v4.md"
THINKING_MODE = "disabled"
COMPLETION_MAX_TOKENS = 1024


class Client:
    def __init__(self, base_url: str, model: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.json_mode_available: bool | None = None

    def chat(self, messages: list[dict[str, str]], json_mode: bool = True) -> tuple[str, int, bool]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": COMPLETION_MAX_TOKENS,
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
        if use_json_mode:
            self.json_mode_available = True
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return content, int(usage.get("total_tokens", max(1, len(content) // 4))), use_json_mode

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


def require_env() -> tuple[str, str, list[str]]:
    missing = [k for k in ("CSDVR_LLM_BASE_URL", "CSDVR_LLM_API_KEY", "CSDVR_LLM_MODEL_A") if not os.getenv(k)]
    if missing:
        raise SystemExit(
            "Missing required postcondition endpoint configuration: "
            + ", ".join(missing)
            + "\nSet CSDVR_LLM_BASE_URL, CSDVR_LLM_API_KEY, CSDVR_LLM_MODEL_A. CSDVR_LLM_MODEL_B is optional."
        )
    models = [os.environ["CSDVR_LLM_MODEL_A"]]
    if os.getenv("CSDVR_LLM_MODEL_B"):
        models.append(os.environ["CSDVR_LLM_MODEL_B"])
    return os.environ["CSDVR_LLM_BASE_URL"].rstrip("/"), os.environ["CSDVR_LLM_API_KEY"], models


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:12]


def raw_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12] if text else ""


def extract_json(text: str) -> dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if "\n" in t:
            t = t.split("\n", 1)[1]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found")
    obj = json.loads(t[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON is not an object")
    return obj


def tasks() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    domains = ["file", "web_form", "table", "workflow_micro"]
    for i in range(80):
        domain = domains[i % len(domains)]
        if domain == "file":
            obj, field, expected = f"reports/draft_{i}.txt", "content", f"approved_{i}"
        elif domain == "web_form":
            obj, field, expected = f"r{i:02d}", "status" if i % 3 else "name", "approved" if i % 3 else f"Alice_{i}"
        elif domain == "table":
            obj, field, expected = f"row{i:02d}", "score", str(80 + i % 10)
        else:
            obj, field, expected = f"step{i:02d}", "note", f"checked_{i}"
        out.append(
            {
                "source": "llm_agent_v4" if i < 40 else "benchmark_sample",
                "task_id": f"pc_v4_{i:02d}",
                "domain": domain,
                "instruction": f"Set {obj}'s {field} to {expected}; preserve every unrelated object and field.",
                "gold_object": obj,
                "gold_field": field,
                "gold_constraint": expected,
                "gold_forbidden": "unrelated object or field changes are forbidden",
            }
        )
    return out


def ask_pc(client: Client, task: dict[str, Any]) -> tuple[dict[str, Any] | None, int, int, str, str, bool]:
    example = {
        "domain": task["domain"],
        "target_object": task["gold_object"],
        "target_field": task["gold_field"],
        "expected_state": task["gold_constraint"],
        "forbidden_side_effects": ["do not modify unrelated objects", "do not modify unrelated fields"],
    }
    system = (
        "Generate a machine-checkable postcondition for a bounded side-effectful task. "
        "Return exactly one JSON object and no prose. Required keys: "
        "domain,target_object,target_field,expected_state,forbidden_side_effects. "
        f"Example JSON: {json.dumps(example, sort_keys=True)}"
    )
    user = {"instruction": task["instruction"], "domain": task["domain"]}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, sort_keys=True)}]
    tokens = 0
    invalid = 0
    raw = ""
    used_json_mode = False
    err = ""
    for _ in range(3):
        try:
            raw, used, mode_used = client.chat(messages, json_mode=True)
            tokens += used
            used_json_mode = used_json_mode or mode_used
            return extract_json(raw), tokens, invalid, raw_hash(raw), "", used_json_mode
        except Exception as exc:
            err = str(exc)
            if "HTTP " in err or "connection error" in err:
                return None, tokens, invalid, raw_hash(raw), err, used_json_mode
            invalid += 1
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Return one valid JSON object only. No markdown or prose."})
    return None, tokens, invalid, raw_hash(raw), err or "invalid postcondition JSON", used_json_mode


def norm(x: Any) -> str:
    return str(x).lower().replace(" ", "").replace("_", "").replace("-", "").replace("/", "")


def score(task: dict[str, Any], pc: dict[str, Any] | None) -> dict[str, float | str]:
    if not pc:
        return {
            "object_accuracy": 0.0,
            "field_accuracy": 0.0,
            "constraint_accuracy": 0.0,
            "forbidden_side_effect_recall": 0.0,
            "constraint_strictness_error": 1.0,
            "pc_error_type": "invalid_json",
        }
    forbidden_raw = pc.get("forbidden_side_effects", [])
    forbidden = " ".join(map(str, forbidden_raw)) if isinstance(forbidden_raw, list) else str(forbidden_raw)
    object_ok = norm(task["gold_object"]) in norm(pc.get("target_object", ""))
    field_ok = norm(task["gold_field"]) in norm(pc.get("target_field", ""))
    constraint_ok = norm(task["gold_constraint"]) in norm(pc.get("expected_state", ""))
    forbidden_ok = any(x in forbidden.lower() for x in ["unrelated", "other", "preserve", "forbidden"])
    strict_error = float(("exactly" in str(pc.get("expected_state", "")).lower() and not constraint_ok) or (field_ok and not object_ok))
    if not object_ok:
        etype = "wrong_object"
    elif not field_ok:
        etype = "wrong_field"
    elif not constraint_ok:
        etype = "wrong_constraint"
    elif not forbidden_ok:
        etype = "missing_forbidden_side_effect"
    elif strict_error:
        etype = "over_strict"
    else:
        etype = "none"
    return {
        "object_accuracy": float(object_ok),
        "field_accuracy": float(field_ok),
        "constraint_accuracy": float(constraint_ok),
        "forbidden_side_effect_recall": float(forbidden_ok),
        "constraint_strictness_error": strict_error,
        "pc_error_type": etype,
    }


def pc_for_mode(task: dict[str, Any], row: dict[str, Any], mode: str) -> dict[str, Any] | None:
    if mode == "Gold-PC":
        return {
            "target_object": task["gold_object"],
            "target_field": task["gold_field"],
            "expected_state": task["gold_constraint"],
            "forbidden_side_effects": [task["gold_forbidden"]],
        }
    if mode == "WrongTarget-PC":
        return {
            "target_object": task["gold_object"] + "_wrong",
            "target_field": task["gold_field"],
            "expected_state": task["gold_constraint"],
            "forbidden_side_effects": [],
        }
    if row.get("generated_postcondition_json"):
        return json.loads(row["generated_postcondition_json"])
    return None


def initial_exec_state(task: dict[str, Any]) -> dict[str, dict[str, str]]:
    target = task["gold_object"]
    field = task["gold_field"]
    return {
        target: {field: "baseline", "untouched": "keep"},
        f"{target}::neighbor": {field: "neighbor", "untouched": "keep"},
    }


def gold_exec_state(task: dict[str, Any], before: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    gold = json.loads(json.dumps(before))
    gold[task["gold_object"]][task["gold_field"]] = task["gold_constraint"]
    return gold


def apply_agent_error(
    task: dict[str, Any],
    before: dict[str, dict[str, str]],
    agent_error: str,
) -> dict[str, dict[str, str]]:
    state = json.loads(json.dumps(before))
    target = task["gold_object"]
    field = task["gold_field"]
    expected = task["gold_constraint"]
    neighbor = f"{target}::neighbor"
    if agent_error == "none":
        state[target][field] = expected
    elif agent_error == "wrong_object":
        state[neighbor][field] = expected
    elif agent_error == "wrong_field":
        state[target]["untouched"] = expected
    elif agent_error == "wrong_constraint":
        state[target][field] = f"{expected}_wrong"
    elif agent_error == "extra_side_effect":
        state[target][field] = expected
        state[neighbor]["untouched"] = "corrupted"
    return state


def executable_outcome(
    before: dict[str, dict[str, str]],
    gold: dict[str, dict[str, str]],
    final: dict[str, dict[str, str]],
) -> tuple[bool, bool]:
    success = final == gold
    residue = False
    object_ids = set(before) | set(gold) | set(final)
    for object_id in object_ids:
        before_obj = before.get(object_id, {})
        gold_obj = gold.get(object_id, {})
        final_obj = final.get(object_id, {})
        for field in set(before_obj) | set(gold_obj) | set(final_obj):
            before_value = before_obj.get(field, "__MISSING__")
            gold_value = gold_obj.get(field, "__MISSING__")
            final_value = final_obj.get(field, "__MISSING__")
            if final_value != gold_value and final_value != before_value:
                residue = True
    return success, residue


def apply_pc_recovery(
    state: dict[str, dict[str, str]],
    before: dict[str, dict[str, str]],
    pc: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, str]], bool]:
    if not pc:
        return state, False
    target = str(pc.get("target_object", ""))
    field = str(pc.get("target_field", ""))
    expected = str(pc.get("expected_state", ""))
    if not target or not field:
        return state, False
    forbidden_raw = pc.get("forbidden_side_effects", [])
    forbidden_text = " ".join(map(str, forbidden_raw)) if isinstance(forbidden_raw, list) else str(forbidden_raw)
    checks_side_effects = any(
        marker in forbidden_text.lower() for marker in ["unrelated", "other", "preserve", "forbidden"]
    )
    target_ok = state.get(target, {}).get(field) == expected
    unexpected_change = False
    for object_id in set(before) | set(state):
        before_obj = before.get(object_id, {})
        current_obj = state.get(object_id, {})
        for current_field in set(before_obj) | set(current_obj):
            if (object_id, current_field) == (target, field):
                continue
            if before_obj.get(current_field, "__MISSING__") != current_obj.get(current_field, "__MISSING__"):
                unexpected_change = True
    repair_trigger = (not target_ok) or (checks_side_effects and unexpected_change)
    if not repair_trigger:
        return state, False

    repaired = json.loads(json.dumps(state))
    if checks_side_effects:
        for object_id in list(set(before) | set(repaired)):
            if object_id not in before:
                if object_id != target:
                    repaired.pop(object_id, None)
                continue
            repaired.setdefault(object_id, {})
            for current_field in list(set(before[object_id]) | set(repaired[object_id])):
                if (object_id, current_field) == (target, field):
                    continue
                if current_field in before[object_id]:
                    repaired[object_id][current_field] = before[object_id][current_field]
                else:
                    repaired[object_id].pop(current_field, None)
    repaired.setdefault(target, {})[field] = expected
    return repaired, True


def run_downstream(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_task_model = {(r["model"], r["task_id"]): r for r in raw}
    task_map = {t["task_id"]: t for t in tasks()}
    for (model, task_id), gen_row in sorted(by_task_model.items()):
        task = task_map[task_id]
        for mode in ["Gold-PC", "LLM-PC", "WrongTarget-PC"]:
            pc = pc_for_mode(task, gen_row, mode)
            sc = score(task, pc)
            for seed in range(5):
                rng = random.Random(f"paired-downstream-{model}-{task_id}-{seed}")
                agent_error = rng.choice(["none", "wrong_object", "wrong_field", "wrong_constraint", "extra_side_effect"])
                before = initial_exec_state(task)
                gold = gold_exec_state(task, before)
                observed = apply_agent_error(task, before, agent_error)
                final, repair_trigger = apply_pc_recovery(observed, before, pc)
                success, residue = executable_outcome(before, gold, final)
                false_repair = agent_error == "none" and repair_trigger and not success
                unnecessary_repair = agent_error == "none" and repair_trigger
                rows.append(
                    {
                        "model": model,
                        "task_id": task_id,
                        "domain": task["domain"],
                        "pc_mode": mode,
                        "seed": seed,
                        "agent_error": agent_error,
                        "success": success,
                        "residue": residue,
                        "false_repair": false_repair,
                        "unnecessary_repair": unnecessary_repair,
                        "repair_trigger": repair_trigger,
                        "initial_state_hash": stable_hash(before),
                        "observed_state_hash": stable_hash(observed),
                        "final_state_hash": stable_hash(final),
                        "object_accuracy": sc["object_accuracy"],
                        "field_accuracy": sc["field_accuracy"],
                        "constraint_accuracy": sc["constraint_accuracy"],
                        "forbidden_side_effect_recall": sc["forbidden_side_effect_recall"],
                    }
                )
    return rows


def summarize(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw:
        groups[row["model"]].append(row)
    out = []
    for model, vals in sorted(groups.items()):
        out.append(
            {
                "model": model,
                "items": len(vals),
                "object_accuracy": mean(float(v["object_accuracy"]) for v in vals),
                "field_accuracy": mean(float(v["field_accuracy"]) for v in vals),
                "constraint_accuracy": mean(float(v["constraint_accuracy"]) for v in vals),
                "forbidden_side_effect_recall": mean(float(v["forbidden_side_effect_recall"]) for v in vals),
                "constraint_strictness_error": mean(float(v["constraint_strictness_error"]) for v in vals),
                "invalid_json_rate": mean(float(v["invalid_json_count"] > 0) for v in vals),
                "token_cost": mean(float(v["token_cost"]) for v in vals),
            }
        )
    return out


def error_taxonomy(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in raw:
        counts[(row["model"], row["domain"], row["pc_error_type"])] += 1
    return [{"model": m, "domain": d, "pc_error_type": e, "count": c} for (m, d, e), c in sorted(counts.items())]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_existing_raw(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    numeric_fields = {
        "object_accuracy",
        "field_accuracy",
        "constraint_accuracy",
        "forbidden_side_effect_recall",
        "constraint_strictness_error",
        "invalid_json_count",
        "json_repair_count",
        "token_cost",
    }
    for row in rows:
        for field in numeric_fields:
            if field in row and row[field] != "":
                row[field] = float(row[field])
    return rows


def write_report(path: Path, summary: list[dict[str, Any]], downstream: list[dict[str, Any]], model_b: bool, smoke: bool = False) -> None:
    target = 160 if model_b else 80
    model_count = len({r["model"] for r in summary})
    lines = [
        "# Postcondition Generation Study v4",
        "",
        f"Expected generation rows under available models: {target}",
        f"Smoke mode: {model_count} model(s) exercised" if smoke else f"Model B available: {model_b}",
        "",
        "| Model | Items | Object acc. | Field acc. | Constraint acc. | Forbidden recall | Strict err. | Invalid JSON | Token |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary:
        lines.append(
            f"| {r['model']} | {r['items']} | {r['object_accuracy']:.3f} | {r['field_accuracy']:.3f} | "
            f"{r['constraint_accuracy']:.3f} | {r['forbidden_side_effect_recall']:.3f} | "
            f"{r['constraint_strictness_error']:.3f} | {r['invalid_json_rate']:.3f} | {r['token_cost']:.1f} |"
        )
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in downstream:
        groups[(row["model"], row["pc_mode"])].append(row)
    lines += [
        "",
        "## Executable downstream C-SDVR validation",
        "",
        "The downstream study replays paired agent errors against mutable structured states; recovery decisions are executed before comparison with a gold final state.",
        "",
        "| Model | PC mode | Runs | Success | Residue | False repair | Unnecessary repair |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for (model, mode), vals in sorted(groups.items()):
        lines.append(
            f"| {model} | {mode} | {len(vals)} | {mean(float(v['success']) for v in vals):.3f} | "
            f"{mean(float(v['residue']) for v in vals):.3f} | {mean(float(v['false_repair']) for v in vals):.3f} | "
            f"{mean(float(v['unnecessary_repair']) for v in vals):.3f} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--smoke-all-models", action="store_true", help="In smoke mode, exercise both configured models.")
    parser.add_argument("--downstream-only", action="store_true", help="Reuse the existing generation CSV and rerun only executable downstream validation.")
    args = parser.parse_args()
    if args.downstream_only:
        if not RAW.exists():
            raise SystemExit(f"Missing existing generation CSV: {RAW}")
        raw = load_existing_raw(RAW)
        down = run_downstream(raw)
        summ = summarize(raw)
        errs = error_taxonomy(raw)
        write_csv(SUMMARY, summ)
        write_csv(ERRORS, errs)
        write_csv(DOWNSTREAM, down)
        write_report(REPORT, summ, down, model_b=len({r['model'] for r in raw}) > 1, smoke=False)
        print(REPORT)
        print(f"postcondition_generation_rows={len(raw)}")
        print(f"postcondition_downstream_rows={len(down)}")
        return
    base, key, models = require_env()
    selected_tasks = tasks()[:4] if args.smoke else tasks()
    if args.smoke and not args.smoke_all_models:
        models = models[:1]
    specs = [(model, task) for model in models for task in selected_tasks]
    workers = 1 if args.smoke else max(1, int(os.getenv("CSDVR_LLM_WORKERS", "4")))

    def run_spec(spec: tuple[str, dict[str, Any]]) -> dict[str, Any]:
        model, task = spec
        client = Client(base, model, key)
        pc, tokens, invalid, rhash, error, json_mode_used = ask_pc(client, task)
        sc = score(task, pc)
        return {
            **task,
            "model": model,
            "generated_postcondition_hash": stable_hash(pc) if pc else "",
            "generated_postcondition_json": json.dumps(pc, sort_keys=True) if pc else "",
            "raw_response_hash": rhash,
            "invalid_json_count": int(pc is None),
            "json_repair_count": invalid,
            "json_mode_used": json_mode_used,
            "token_cost": tokens,
            "error": error,
            **sc,
        }

    raw: list[dict[str, Any]] = []
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_spec, spec) for spec in specs]
            for fut in as_completed(futures):
                raw.append(fut.result())
                if len(raw) % 20 == 0:
                    print(f"postcondition_progress={len(raw)}", flush=True)
    else:
        for spec in specs:
            raw.append(run_spec(spec))
            if len(raw) % 20 == 0:
                print(f"postcondition_progress={len(raw)}", flush=True)
    raw.sort(key=lambda r: (r["model"], r["task_id"]))
    down = run_downstream(raw)
    summ = summarize(raw)
    errs = error_taxonomy(raw)
    if args.smoke:
        write_csv(SMOKE_RAW, raw)
        write_csv(SMOKE_SUMMARY, summ)
        write_csv(SMOKE_ERRORS, errs)
        write_csv(SMOKE_DOWNSTREAM, down)
        write_report(SMOKE_REPORT, summ, down, model_b=False, smoke=True)
        print(SMOKE_REPORT)
    else:
        write_csv(RAW, raw)
        write_csv(SUMMARY, summ)
        write_csv(ERRORS, errs)
        write_csv(DOWNSTREAM, down)
        write_report(REPORT, summ, down, model_b=len(models) > 1, smoke=False)
        print(REPORT)
    print(f"postcondition_generation_rows={len(raw)}")


if __name__ == "__main__":
    main()
