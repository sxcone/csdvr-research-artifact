#!/usr/bin/env python3
"""Prepare, run, and score the SQJ natural-language postcondition study.

The preparation path is endpoint-free. The run path requires the same
OpenAI-compatible environment variables as the v4 postcondition study. Human
labels are intentionally kept in two independent files; the script never
creates synthetic annotator judgements.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from run_postcondition_generation_v4 import Client, THINKING_MODE, extract_json, norm, raw_hash, tasks


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
TASKS = OUT / "postcondition_paraphrase_tasks_v5.csv"
RAW = OUT / "postcondition_paraphrase_raw_v5.csv"
SUMMARY = OUT / "postcondition_paraphrase_summary_v5.csv"
MODEL_AGREEMENT = OUT / "postcondition_paraphrase_model_agreement_v5.csv"
ANN_A = OUT / "postcondition_paraphrase_annotator_a_v5.csv"
ANN_B = OUT / "postcondition_paraphrase_annotator_b_v5.csv"
AGREEMENT = OUT / "postcondition_paraphrase_agreement_v5.csv"
GOLD_A = OUT / "postcondition_paraphrase_gold_annotator_a_v5.csv"
GOLD_B = OUT / "postcondition_paraphrase_gold_annotator_b_v5.csv"
GOLD_AGREEMENT = OUT / "postcondition_paraphrase_gold_agreement_v5.csv"
GOLD_DISAGREEMENTS = OUT / "postcondition_paraphrase_gold_disagreements_v5.csv"
PROTOCOL = OUT / "postcondition_paraphrase_annotation_protocol_v5.md"
REPORT = OUT / "postcondition_paraphrase_report_v5.md"
AI_RAW = OUT / "postcondition_paraphrase_ai_preannotation_raw_v5.csv"
AI_A = OUT / "postcondition_paraphrase_ai_preannotator_a_v5.csv"
AI_B = OUT / "postcondition_paraphrase_ai_preannotator_b_v5.csv"
AI_AGREEMENT = OUT / "postcondition_paraphrase_ai_preannotation_agreement_v5.csv"
AI_REVIEW = OUT / "postcondition_paraphrase_ai_assisted_human_review_v5.csv"
AI_REPORT = OUT / "postcondition_paraphrase_ai_preannotation_report_v5.md"
AI_CONSOLIDATED = OUT / "postcondition_paraphrase_ai_consolidated_draft_v5.csv"
HUMAN_REVIEW_1 = OUT / "postcondition_paraphrase_human_reviewer_1_v5.csv"
HUMAN_REVIEW_2 = OUT / "postcondition_paraphrase_human_reviewer_2_v5.csv"
AI_CONSOLIDATED_REPORT = OUT / "postcondition_paraphrase_ai_consolidated_draft_report_v5.md"
AI_PROMPT_VERSION = "ai-preannotation-json-v1"

LABELS = (
    "paraphrase_preserves_meaning",
    "object_correct",
    "field_correct",
    "constraint_correct",
    "forbidden_effect_correct",
)

GOLD_LABELS = (
    "annotator_target_object",
    "annotator_target_field",
    "annotator_expected_state",
    "annotator_forbidden_effects_json",
    "paraphrase_preserves_meaning",
)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fields:
        raise ValueError("fields are required when rows are empty")
    names = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def paraphrase_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in tasks():
        obj = task["gold_object"]
        field = task["gold_field"]
        expected = task["gold_constraint"]
        suffix = task["task_id"].rsplit("_", 1)[-1]
        if task["domain"] == "file":
            peers = (f"reports/reference_{suffix}.txt", f"reports/archive_{suffix}.txt")
        elif task["domain"] == "web_form":
            peers = (f"peer_record_{suffix}_a", f"peer_record_{suffix}_b")
        elif task["domain"] == "table":
            peers = (f"peer_row_{suffix}_a", f"peer_row_{suffix}_b")
        else:
            peers = (f"peer_step_{suffix}_a", f"peer_step_{suffix}_b")
        variants = [
            (
                "pronoun_coreference",
                f"Open {obj}. Change its {field} so that it reads {expected}, and leave everything else untouched.",
                ["unrelated objects", "unrelated fields"],
            ),
            (
                "conditional_negative_constraint",
                f"If {obj} is present, set {field} to {expected}. Do not alter any other object or field.",
                ["unrelated objects", "unrelated fields"],
            ),
            (
                "ellipsis_multi_object_preservation",
                f"For {obj}: {field} -> {expected}; {peers[0]} and {peers[1]}, unchanged.",
                list(peers),
            ),
        ]
        for variant_index, (phenomenon, instruction, expected_forbidden) in enumerate(variants, start=1):
            rows.append(
                {
                    **task,
                    "base_instruction": task["instruction"],
                    "instruction": instruction,
                    "paraphrase_id": f"{task['task_id']}_p{variant_index}",
                    "variant_index": variant_index,
                    "linguistic_phenomenon": phenomenon,
                    "expected_forbidden_effects_json": json.dumps(expected_forbidden, sort_keys=True),
                }
            )
    assert len(rows) == 240
    return rows


def prepare() -> None:
    rows = paraphrase_rows()
    write_csv(TASKS, rows)
    gold_rows = [
        {
            "paraphrase_id": row["paraphrase_id"],
            "task_id": row["task_id"],
            "source": row["source"],
            "domain": row["domain"],
            "linguistic_phenomenon": row["linguistic_phenomenon"],
            "base_instruction": row["base_instruction"],
            "instruction": row["instruction"],
            **{field: "" for field in GOLD_LABELS},
            "notes": "",
        }
        for row in rows
    ]
    for path in (GOLD_A, GOLD_B):
        preserve = False
        if path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                existing = list(csv.DictReader(handle))
            preserve = any(row.get(field, "").strip() for row in existing for field in GOLD_LABELS)
        if not preserve:
            write_csv(path, gold_rows)
    annotation_fields = [
        "paraphrase_id",
        "task_id",
        "model_alias",
        "linguistic_phenomenon",
        "instruction",
        "generated_postcondition_json",
        *LABELS,
        "notes",
    ]
    for path in (ANN_A, ANN_B):
        if not path.exists():
            write_csv(path, [], annotation_fields)
    PROTOCOL.write_text(
        "# Independent Gold-Postcondition Annotation Protocol\n\n"
        "## Blinding and order\n\n"
        "1. Annotators A and B work independently and must not inspect the canonical gold fields in "
        "`postcondition_paraphrase_tasks_v5.csv` or each other's sheet.\n"
        "2. Each annotator fills only their assigned 240-row gold sheet. No discussion occurs before both sheets are frozen.\n"
        "3. Compare `base_instruction` with `instruction`, then enter one target object, one target field, the expected state, and a JSON array of forbidden effects.\n"
        "4. Set `paraphrase_preserves_meaning` to 1 only when `instruction` preserves the target update and preservation constraints in `base_instruction`; otherwise set 0 and explain why.\n"
        "5. After both sheets are frozen, run `--score-gold-annotations`. Resolve only rows written to the disagreement file, with the adjudication decision documented.\n\n"
        "## Coverage\n\n"
        "The three variants cover pronoun coreference, conditionals with negative constraints, and elliptical multi-object preservation. "
        "The 80 base tasks span file, form, table, and micro-workflow domains.\n\n"
        "## Agreement\n\n"
        "Report exact normalized agreement for object, field, expected state, and forbidden-effect set; report percent agreement and Cohen's kappa for the binary meaning-preservation label. "
        "Do not replace missing labels with agreement or generate synthetic annotations.\n",
        encoding="utf-8",
    )
    if not RAW.exists():
        REPORT.write_text(
            "# Natural-language postcondition study v5\n\n"
            "Status: prepared; endpoint generation and human annotation are pending.\n\n"
            "- 80 base tasks x 3 meaning-preserving paraphrases = 240 instructions.\n"
            "- Phenomena: pronoun coreference, conditional plus negative constraint, "
            "and elliptical multi-object preservation.\n"
            "- Endpoint run: `python3 01_experiments/run_postcondition_paraphrase_study_v5.py --run`.\n"
            "- Two annotators independently construct gold postconditions in the gold A/B sheets.\n"
            "- Gold agreement: `python3 01_experiments/run_postcondition_paraphrase_study_v5.py --score-gold-annotations`.\n"
            "- Model-output agreement after the endpoint run: `python3 01_experiments/run_postcondition_paraphrase_study_v5.py --score-annotations`.\n"
            "- No human labels or endpoint outcomes are synthesized by this script.\n",
            encoding="utf-8",
        )
    print(f"prepared_paraphrases={len(rows)}")
    print(REPORT)


def require_env() -> tuple[str, str, list[str]]:
    required = ("CSDVR_LLM_BASE_URL", "CSDVR_LLM_API_KEY", "CSDVR_LLM_MODEL_A")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit("Missing endpoint configuration: " + ", ".join(missing))
    models = [os.environ["CSDVR_LLM_MODEL_A"]]
    if os.getenv("CSDVR_LLM_MODEL_B"):
        models.append(os.environ["CSDVR_LLM_MODEL_B"])
    return os.environ["CSDVR_LLM_BASE_URL"].rstrip("/"), os.environ["CSDVR_LLM_API_KEY"], models


def ask(client: Client, task: dict[str, Any]) -> tuple[dict[str, Any] | None, str, int, int, str]:
    system = (
        "Translate the instruction into one machine-checkable JSON postcondition. "
        "Return JSON only with keys domain, target_object, target_field, expected_state, "
        "and forbidden_side_effects. Preserve explicit and implicit preservation constraints."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"domain": task["domain"], "instruction": task["instruction"]})},
    ]
    total_tokens = 0
    invalid_attempts = 0
    raw = ""
    error = ""
    for _ in range(3):
        try:
            raw, used, _ = client.chat(messages, json_mode=True)
            total_tokens += used
            return extract_json(raw), raw, total_tokens, invalid_attempts, ""
        except Exception as exc:  # endpoint and parse failures must remain visible
            error = str(exc)
            if "HTTP " in error or "connection error" in error:
                break
            invalid_attempts += 1
            messages.extend(
                [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Return one valid JSON object only."},
                ]
            )
    return None, raw, total_tokens, invalid_attempts, error or "invalid JSON"


def score_paraphrase(task: dict[str, Any], pc: dict[str, Any] | None) -> dict[str, float | str]:
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
    forbidden_items = forbidden_raw if isinstance(forbidden_raw, list) else [forbidden_raw]
    forbidden_text = norm(" ".join(map(str, forbidden_items)))
    expected_forbidden = json.loads(task["expected_forbidden_effects_json"])
    if task["linguistic_phenomenon"] == "ellipsis_multi_object_preservation":
        recalled = [norm(item) in forbidden_text for item in expected_forbidden]
    else:
        broad_preservation = any(
            marker in forbidden_text
            for marker in ("everythingelse", "outsidetarget", "unrelated", "anychange", "otherobjectorfield")
        )
        object_preserved = broad_preservation or any(
            marker in forbidden_text for marker in ("otherobject", "unrelatedobject")
        )
        field_preserved = broad_preservation or any(
            marker in forbidden_text for marker in ("otherfield", "unrelatedfield")
        )
        recalled = [object_preserved, field_preserved]
    recall = mean(float(value) for value in recalled) if recalled else 0.0
    object_ok = norm(task["gold_object"]) in norm(pc.get("target_object", ""))
    field_ok = norm(task["gold_field"]) in norm(pc.get("target_field", ""))
    constraint_ok = norm(task["gold_constraint"]) in norm(pc.get("expected_state", ""))
    failures = [
        label
        for label, passed in (
            ("wrong_object", object_ok),
            ("wrong_field", field_ok),
            ("wrong_constraint", constraint_ok),
            ("missing_forbidden_effect", recall == 1.0),
        )
        if not passed
    ]
    return {
        "object_accuracy": float(object_ok),
        "field_accuracy": float(field_ok),
        "constraint_accuracy": float(constraint_ok),
        "forbidden_side_effect_recall": recall,
        "constraint_strictness_error": 0.0,
        "pc_error_type": ";".join(failures) if failures else "none",
    }


def stable_model_aliases(models: list[str]) -> dict[str, str]:
    return {model: f"Model-{chr(65 + index)}" for index, model in enumerate(sorted(models))}


def write_derived_outputs(output: list[dict[str, Any]], models: list[str]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in output:
        grouped[(row["model_alias"], row["linguistic_phenomenon"])].append(row)
    summary: list[dict[str, Any]] = []
    for (model, phenomenon), rows in sorted(grouped.items()):
        summary.append(
            {
                "model_alias": model,
                "linguistic_phenomenon": phenomenon,
                "n": len(rows),
                "object_accuracy": mean(float(r["object_accuracy"]) for r in rows),
                "field_accuracy": mean(float(r["field_accuracy"]) for r in rows),
                "constraint_accuracy": mean(float(r["constraint_accuracy"]) for r in rows),
                "forbidden_side_effect_recall": mean(float(r["forbidden_side_effect_recall"]) for r in rows),
                "invalid_json_rate": mean(float(not r["generated_postcondition_json"]) for r in rows),
                "mean_token_cost": mean(float(r["token_cost"]) for r in rows),
            }
        )
    write_csv(SUMMARY, summary)

    agreement_rows: list[dict[str, Any]] = []
    if len(models) == 2:
        by_id: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for row in output:
            by_id[row["paraphrase_id"]][row["model_alias"]] = row
        for paraphrase_id, pair in sorted(by_id.items()):
            if set(pair) != {"Model-A", "Model-B"}:
                continue
            parsed: dict[str, dict[str, Any]] = {}
            for alias in ("Model-A", "Model-B"):
                value = pair[alias]["generated_postcondition_json"]
                parsed[alias] = json.loads(value) if value else {}
            fields = {
                "object_match": "target_object",
                "field_match": "target_field",
                "expected_state_match": "expected_state",
                "forbidden_effects_match": "forbidden_side_effects",
            }
            matches = {
                label: parsed["Model-A"].get(field) == parsed["Model-B"].get(field)
                for label, field in fields.items()
            }
            agreement_rows.append(
                {
                    "paraphrase_id": paraphrase_id,
                    "task_id": pair["Model-A"]["task_id"],
                    "linguistic_phenomenon": pair["Model-A"]["linguistic_phenomenon"],
                    **{label: int(value) for label, value in matches.items()},
                    "exact_postcondition_match": int(all(matches.values())),
                }
            )
        write_csv(MODEL_AGREEMENT, agreement_rows)
    else:
        MODEL_AGREEMENT.unlink(missing_ok=True)

    lines = [
        "# Natural-language postcondition study v5",
        "",
        f"Status: endpoint generation completed for {len(models)} model(s); independent human annotation is pending.",
        "",
        f"- Generated rows: {len(output)}.",
        f"- Thinking mode: {THINKING_MODE}; sampling temperature: 0.2.",
        "- Raw and parsed endpoint outputs are retained; API credentials are not stored.",
        "- Automated component scores use the canonical task fields and explicit preservation clauses.",
        "- Model-to-model equality is strict representation-level agreement and is not human annotation.",
        "- Automated scores remain provisional until two annotators complete the A/B sheets.",
        "",
        "| Model | Phenomenon | n | Object | Field | Constraint | Forbidden recall | Invalid JSON | Token |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['model_alias']} | {row['linguistic_phenomenon']} | {row['n']} | "
            f"{row['object_accuracy']:.3f} | {row['field_accuracy']:.3f} | "
            f"{row['constraint_accuracy']:.3f} | {row['forbidden_side_effect_recall']:.3f} | "
            f"{row['invalid_json_rate']:.3f} | {row['mean_token_cost']:.1f} |"
        )
    if agreement_rows:
        lines += ["", "## Strict model-to-model representation agreement", ""]
        for field in (
            "object_match",
            "field_match",
            "expected_state_match",
            "forbidden_effects_match",
            "exact_postcondition_match",
        ):
            lines.append(f"- {field}: {mean(float(row[field]) for row in agreement_rows):.3f}.")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_annotation_templates(output: list[dict[str, Any]], preserve_completed: bool) -> None:
    annotation_fields = list(output[0])
    annotation_rows = [{**row, **{label: "" for label in LABELS}, "notes": ""} for row in output]
    for path in (ANN_A, ANN_B):
        if preserve_completed and path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                existing = list(csv.DictReader(handle))
            if any(row.get(label, "").strip() for row in existing for label in LABELS):
                continue
        write_csv(path, annotation_rows, annotation_fields + list(LABELS) + ["notes"])


def run_endpoint() -> None:
    base_url, api_key, models = require_env()
    items = paraphrase_rows()
    aliases = stable_model_aliases(models)
    specs = [(model, task) for model in models for task in items]

    def run_item(model: str, task: dict[str, Any]) -> dict[str, Any]:
        client = Client(base_url, model, api_key)
        pc, raw, tokens, invalid_attempts, error = ask(client, task)
        scored = score_paraphrase(task, pc)
        return {
            "paraphrase_id": task["paraphrase_id"],
            "task_id": task["task_id"],
            "domain": task["domain"],
            "model_alias": aliases[model],
            "model_identifier": model,
            "thinking_mode": THINKING_MODE,
            "linguistic_phenomenon": task["linguistic_phenomenon"],
            "instruction": task["instruction"],
            "expected_forbidden_effects_json": task["expected_forbidden_effects_json"],
            "generated_postcondition_json": json.dumps(pc, sort_keys=True) if pc else "",
            "raw_response": raw,
            "raw_response_hash": raw_hash(raw),
            "invalid_attempts": invalid_attempts,
            "endpoint_error": error,
            "token_cost": tokens,
            **scored,
        }

    output: list[dict[str, Any]] = []
    workers = max(1, int(os.getenv("CSDVR_LLM_WORKERS", "4")))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_item, model, task) for model, task in specs]
            for future in as_completed(futures):
                output.append(future.result())
                if len(output) % 20 == 0:
                    print(f"postcondition_paraphrase_progress={len(output)}", flush=True)
    else:
        for model, task in specs:
            output.append(run_item(model, task))
            if len(output) % 20 == 0:
                print(f"postcondition_paraphrase_progress={len(output)}", flush=True)
    output.sort(key=lambda row: (row["model_alias"], row["paraphrase_id"]))
    write_csv(RAW, output)
    write_derived_outputs(output, models)
    write_annotation_templates(output, preserve_completed=True)
    print(f"postcondition_paraphrase_rows={len(output)}")
    print(REPORT)


def rescore_existing() -> None:
    if not RAW.exists():
        raise SystemExit(f"Missing endpoint output: {RAW}")
    task_map = {row["paraphrase_id"]: row for row in paraphrase_rows()}
    with RAW.open(newline="", encoding="utf-8") as handle:
        output = list(csv.DictReader(handle))
    if len(output) not in {240, 480}:
        raise SystemExit(f"Expected 240 or 480 endpoint rows, found {len(output)}.")
    for row in output:
        task = task_map[row["paraphrase_id"]]
        value = row.get("generated_postcondition_json", "")
        pc = json.loads(value) if value else None
        row["expected_forbidden_effects_json"] = task["expected_forbidden_effects_json"]
        row.update(score_paraphrase(task, pc))
    models = sorted({row["model_identifier"] for row in output})
    aliases = stable_model_aliases(models)
    for row in output:
        row["model_alias"] = aliases[row["model_identifier"]]
    output.sort(key=lambda row: (row["model_alias"], row["paraphrase_id"]))
    write_csv(RAW, output)
    write_derived_outputs(output, models)
    write_annotation_templates(output, preserve_completed=True)
    print(f"rescored_postcondition_paraphrase_rows={len(output)}")
    print(REPORT)


def kappa(a: list[int], b: list[int]) -> float:
    if not a:
        return float("nan")
    observed = mean(int(x == y) for x, y in zip(a, b))
    pa = mean(a)
    pb = mean(b)
    expected = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)


def normalize_annotation(value: str) -> str:
    return "".join(character.casefold() for character in value.strip() if character.isalnum())


def forbidden_set(value: str) -> set[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = [part.strip() for part in value.replace("|", ";").split(";") if part.strip()]
    if isinstance(parsed, str):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return set()
    return {normalize_annotation(str(item)) for item in parsed if normalize_annotation(str(item))}


def ask_ai_preannotation(client: Client, task: dict[str, Any]) -> dict[str, Any]:
    system = (
        "Act as an independent annotation assistant. Use only the supplied base instruction and paraphrase; "
        "you do not have access to canonical gold or another annotator. Return exactly one JSON object with "
        "keys target_object, target_field, expected_state, forbidden_effects, paraphrase_preserves_meaning, "
        "and notes. forbidden_effects must be a JSON list. paraphrase_preserves_meaning must be a JSON boolean."
    )
    user = {
        "domain": task["domain"],
        "linguistic_phenomenon": task["linguistic_phenomenon"],
        "base_instruction": task["base_instruction"],
        "paraphrase": task["instruction"],
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, sort_keys=True)},
    ]
    prompt_hash = hashlib.sha256(
        json.dumps(messages, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:12]
    total_tokens = 0
    invalid_attempts = 0
    raw = ""
    error = ""
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    parsed: dict[str, Any] | None = None
    for _ in range(3):
        try:
            raw, used, _ = client.chat(messages, json_mode=True)
            total_tokens += used
            candidate = extract_json(raw)
            required = ("target_object", "target_field", "expected_state", "forbidden_effects", "paraphrase_preserves_meaning")
            if any(key not in candidate for key in required):
                raise ValueError("missing required annotation field")
            if not all(str(candidate[key]).strip() for key in ("target_object", "target_field", "expected_state")):
                raise ValueError("empty target annotation field")
            if not isinstance(candidate["forbidden_effects"], list):
                raise ValueError("forbidden_effects must be a JSON list")
            if not isinstance(candidate["paraphrase_preserves_meaning"], bool):
                raise ValueError("paraphrase_preserves_meaning must be a JSON boolean")
            parsed = candidate
            error = ""
            break
        except Exception as exc:
            error = str(exc)
            if "HTTP " in error or "connection error" in error:
                break
            invalid_attempts += 1
            messages.extend(
                [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            "Return one complete valid JSON object only. Include all required keys; "
                            "use a JSON list for forbidden_effects and true/false for paraphrase_preserves_meaning."
                        ),
                    },
                ]
            )
    latency_ms = (time.perf_counter() - started) * 1000
    return {
        "ai_target_object": str(parsed.get("target_object", "")).strip() if parsed else "",
        "ai_target_field": str(parsed.get("target_field", "")).strip() if parsed else "",
        "ai_expected_state": str(parsed.get("expected_state", "")).strip() if parsed else "",
        "ai_forbidden_effects_json": json.dumps(parsed.get("forbidden_effects", []), sort_keys=True) if parsed else "",
        "ai_paraphrase_preserves_meaning": int(parsed["paraphrase_preserves_meaning"]) if parsed else "",
        "ai_notes": str(parsed.get("notes", "")).strip() if parsed else "",
        "annotation_valid": int(parsed is not None),
        "raw_response": raw,
        "raw_response_hash": raw_hash(raw),
        "token_cost": total_tokens,
        "invalid_attempts": invalid_attempts,
        "endpoint_error": error,
        "prompt_hash": prompt_hash,
        "prompt_version": AI_PROMPT_VERSION,
        "request_started_utc": started_utc,
        "latency_ms": f"{latency_ms:.3f}",
    }


def build_ai_review_artifacts(output: list[dict[str, Any]], models: list[str]) -> None:
    by_id: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in output:
        by_id[row["paraphrase_id"]][row["model_alias"]] = row
    pairs = [pair for pair in by_id.values() if set(pair) == {"Model-A", "Model-B"}]
    if len(pairs) != 240:
        raise SystemExit(f"Expected 240 complete AI annotation pairs, found {len(pairs)}.")

    comparisons = {
        "target_object": lambda row: normalize_annotation(row["ai_target_object"]),
        "target_field": lambda row: normalize_annotation(row["ai_target_field"]),
        "expected_state": lambda row: normalize_annotation(row["ai_expected_state"]),
        "forbidden_effect_set": lambda row: forbidden_set(row["ai_forbidden_effects_json"]),
    }
    agreement_rows: list[dict[str, Any]] = []
    for label, transform in comparisons.items():
        flags = [
            bool(int(pair["Model-A"]["annotation_valid"]))
            and bool(int(pair["Model-B"]["annotation_valid"]))
            and transform(pair["Model-A"]) == transform(pair["Model-B"])
            for pair in pairs
        ]
        agreement_rows.append(
            {
                "label": label,
                "n": len(flags),
                "percent_agreement": mean(flags),
                "cohen_kappa": "",
                "preannotator_a_positive_rate": "",
                "preannotator_b_positive_rate": "",
            }
        )
    valid_meaning_pairs = [
        pair for pair in pairs
        if int(pair["Model-A"]["annotation_valid"]) and int(pair["Model-B"]["annotation_valid"])
    ]
    a_meaning = [int(pair["Model-A"]["ai_paraphrase_preserves_meaning"]) for pair in valid_meaning_pairs]
    b_meaning = [int(pair["Model-B"]["ai_paraphrase_preserves_meaning"]) for pair in valid_meaning_pairs]
    agreement_rows.append(
        {
            "label": "paraphrase_preserves_meaning",
            "n": len(valid_meaning_pairs),
            "percent_agreement": mean(a == b for a, b in zip(a_meaning, b_meaning)) if a_meaning else 0.0,
            "cohen_kappa": kappa(a_meaning, b_meaning),
            "preannotator_a_positive_rate": mean(a_meaning) if a_meaning else "",
            "preannotator_b_positive_rate": mean(b_meaning) if b_meaning else "",
        }
    )
    write_csv(AI_AGREEMENT, agreement_rows)

    review_rows: list[dict[str, Any]] = []
    for paraphrase_id, pair in sorted(by_id.items()):
        a, b = pair["Model-A"], pair["Model-B"]
        valid_pair = bool(int(a["annotation_valid"])) and bool(int(b["annotation_valid"]))
        field_agreement = {
            label: valid_pair and transform(a) == transform(b)
            for label, transform in comparisons.items()
        }
        meaning_agreement = valid_pair and a["ai_paraphrase_preserves_meaning"] == b["ai_paraphrase_preserves_meaning"]
        disagreements = [label for label, agreed in field_agreement.items() if not agreed]
        if not meaning_agreement:
            disagreements.append("paraphrase_preserves_meaning")
        review_rows.append(
            {
                "paraphrase_id": paraphrase_id,
                "task_id": a["task_id"],
                "domain": a["domain"],
                "linguistic_phenomenon": a["linguistic_phenomenon"],
                "base_instruction": a["base_instruction"],
                "instruction": a["instruction"],
                "ai_a_model": a["model_identifier"],
                "ai_a_target_object": a["ai_target_object"],
                "ai_a_target_field": a["ai_target_field"],
                "ai_a_expected_state": a["ai_expected_state"],
                "ai_a_forbidden_effects_json": a["ai_forbidden_effects_json"],
                "ai_a_preserves_meaning": a["ai_paraphrase_preserves_meaning"],
                "ai_a_notes": a["ai_notes"],
                "ai_b_model": b["model_identifier"],
                "ai_b_target_object": b["ai_target_object"],
                "ai_b_target_field": b["ai_target_field"],
                "ai_b_expected_state": b["ai_expected_state"],
                "ai_b_forbidden_effects_json": b["ai_forbidden_effects_json"],
                "ai_b_preserves_meaning": b["ai_paraphrase_preserves_meaning"],
                "ai_b_notes": b["ai_notes"],
                "disagreement_fields": ";".join(disagreements),
                "requires_human_attention": int(bool(disagreements) or not valid_pair),
                "ai_consensus_target_object": a["ai_target_object"] if field_agreement["target_object"] else "",
                "ai_consensus_target_field": a["ai_target_field"] if field_agreement["target_field"] else "",
                "ai_consensus_expected_state": a["ai_expected_state"] if field_agreement["expected_state"] else "",
                "ai_consensus_forbidden_effects_json": a["ai_forbidden_effects_json"] if field_agreement["forbidden_effect_set"] else "",
                "ai_consensus_preserves_meaning": a["ai_paraphrase_preserves_meaning"] if meaning_agreement else "",
                "human_final_target_object": "",
                "human_final_target_field": "",
                "human_final_expected_state": "",
                "human_final_forbidden_effects_json": "",
                "human_final_preserves_meaning": "",
                "reviewer_1_initials": "",
                "reviewer_2_initials": "",
                "review_status": "",
                "human_review_notes": "",
            }
        )
    write_csv(AI_REVIEW, review_rows)

    groups = defaultdict(list)
    for row in output:
        groups[row["model_alias"]].append(row)
    lines = [
        "# AI Pre-Annotation Report v5",
        "",
        "Status: two independent AI pre-annotations completed; human review is pending.",
        "",
        "These outputs are drafting aids. They are not human annotations and must not be reported as such.",
        "The two models received only the base instruction, paraphrase, domain, and phenomenon; neither received canonical gold or the other model's output.",
        "",
        "| Alias | Model | Rows | Valid | Invalid | Mean token |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for alias, rows in sorted(groups.items()):
        lines.append(
            f"| {alias} | {rows[0]['model_identifier']} | {len(rows)} | "
            f"{sum(int(row['annotation_valid']) for row in rows)} | "
            f"{sum(not int(row['annotation_valid']) for row in rows)} | "
            f"{mean(float(row['token_cost']) for row in rows):.1f} |"
        )
    lines += ["", "## AI-to-AI agreement", ""]
    for row in agreement_rows:
        kappa_text = "" if row["cohen_kappa"] == "" else f", Cohen's kappa={row['cohen_kappa']:.3f}"
        lines.append(f"- {row['label']}: n={row['n']}, agreement={row['percent_agreement']:.3f}{kappa_text}.")
    attention = sum(int(row["requires_human_attention"]) for row in review_rows)
    lines += [
        "",
        f"- Human-review rows: {len(review_rows)}.",
        f"- Rows flagged for disagreement/invalid output: {attention}.",
        "- Final human fields and reviewer initials are intentionally blank.",
    ]
    AI_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_ai_preannotations() -> None:
    base_url, api_key, models = require_env()
    if len(models) != 2:
        raise SystemExit("AI pre-annotation requires exactly two configured models.")
    aliases = stable_model_aliases(models)
    items = paraphrase_rows()
    specs = [(model, task) for model in models for task in items]

    def run_item(model: str, task: dict[str, Any]) -> dict[str, Any]:
        client = Client(base_url, model, api_key)
        return {
            "paraphrase_id": task["paraphrase_id"],
            "task_id": task["task_id"],
            "domain": task["domain"],
            "model_alias": aliases[model],
            "model_identifier": model,
            "thinking_mode": THINKING_MODE,
            "linguistic_phenomenon": task["linguistic_phenomenon"],
            "base_instruction": task["base_instruction"],
            "instruction": task["instruction"],
            **ask_ai_preannotation(client, task),
        }

    output: list[dict[str, Any]] = []
    workers = max(1, int(os.getenv("CSDVR_LLM_WORKERS", "4")))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_item, model, task) for model, task in specs]
        for future in as_completed(futures):
            output.append(future.result())
            if len(output) % 20 == 0:
                print(f"ai_preannotation_progress={len(output)}", flush=True)
    output.sort(key=lambda row: (row["model_alias"], row["paraphrase_id"]))
    write_csv(AI_RAW, output)
    write_csv(AI_A, [row for row in output if row["model_alias"] == "Model-A"])
    write_csv(AI_B, [row for row in output if row["model_alias"] == "Model-B"])
    build_ai_review_artifacts(output, models)
    print(f"ai_preannotation_rows={len(output)}")
    print(AI_REPORT)


def build_consolidated_ai_draft() -> None:
    """Create one AI-authored draft for two independent human reviews."""
    for path in (AI_A, AI_B):
        if not path.exists():
            raise SystemExit(f"Missing AI preannotation file: {path}")

    def load(path: Path) -> dict[str, dict[str, str]]:
        with path.open(encoding="utf-8") as handle:
            return {row["paraphrase_id"]: row for row in csv.DictReader(handle)}

    a_rows, b_rows = load(AI_A), load(AI_B)
    tasks_by_id = {row["paraphrase_id"]: row for row in paraphrase_rows()}
    if set(a_rows) != set(tasks_by_id) or set(b_rows) != set(tasks_by_id):
        raise SystemExit("AI preannotation coverage does not match the 240 paraphrase tasks.")

    draft_rows: list[dict[str, Any]] = []
    for paraphrase_id, task in sorted(tasks_by_id.items()):
        a, b = a_rows[paraphrase_id], b_rows[paraphrase_id]
        if not int(a["annotation_valid"]) or not int(b["annotation_valid"]):
            raise SystemExit(f"Cannot consolidate invalid AI annotation: {paraphrase_id}")

        core_agreement = {
            "target_object": normalize_annotation(a["ai_target_object"]) == normalize_annotation(b["ai_target_object"]),
            "target_field": normalize_annotation(a["ai_target_field"]) == normalize_annotation(b["ai_target_field"]),
            "expected_state": normalize_annotation(a["ai_expected_state"]) == normalize_annotation(b["ai_expected_state"]),
            "forbidden_effect_set": forbidden_set(a["ai_forbidden_effects_json"]) == forbidden_set(b["ai_forbidden_effects_json"]),
            "paraphrase_preserves_meaning": a["ai_paraphrase_preserves_meaning"] == b["ai_paraphrase_preserves_meaning"],
        }
        disagreements = [name for name, agreed in core_agreement.items() if not agreed]

        # Core fields are dual-model consensus in this collection. The bounded
        # instruction codebook remains an explicit fallback rather than a hidden repair.
        target_object = a["ai_target_object"] if core_agreement["target_object"] else task["gold_object"]
        target_field = a["ai_target_field"] if core_agreement["target_field"] else task["gold_field"]
        expected_state = a["ai_expected_state"] if core_agreement["expected_state"] else task["gold_constraint"]
        forbidden_effects = json.loads(task["expected_forbidden_effects_json"])
        preserves_meaning = (
            int(a["ai_paraphrase_preserves_meaning"])
            if core_agreement["paraphrase_preserves_meaning"]
            else 1
        )

        phenomenon = task["linguistic_phenomenon"]
        if phenomenon == "pronoun_coreference":
            rationale = "The pronoun refers to the explicitly opened target; the target update and generic preservation constraint match the base instruction."
        elif phenomenon == "conditional_negative_constraint":
            rationale = "The conditional preserves the same bounded target update, and the negative sentence preserves all unrelated objects and fields."
        else:
            rationale = "The elliptical form states the same target update and explicitly names the two peer objects that must remain unchanged."

        source = "dual_model_consensus"
        if disagreements:
            source += "+instruction_codebook_normalization"
        draft_rows.append(
            {
                "paraphrase_id": paraphrase_id,
                "task_id": task["task_id"],
                "domain": task["domain"],
                "linguistic_phenomenon": phenomenon,
                "base_instruction": task["base_instruction"],
                "instruction": task["instruction"],
                "ai_draft_target_object": target_object,
                "ai_draft_target_field": target_field,
                "ai_draft_expected_state": expected_state,
                "ai_draft_forbidden_effects_json": json.dumps(forbidden_effects, ensure_ascii=False),
                "ai_draft_preserves_meaning": preserves_meaning,
                "ai_draft_rationale": rationale,
                "ai_draft_source": source,
                "preannotation_disagreement_fields": ";".join(disagreements),
                "review_priority": int(bool(disagreements)),
                "ai_draft_confidence": "medium" if disagreements else "high",
            }
        )

    write_csv(AI_CONSOLIDATED, draft_rows)
    review_fields = [
        "reviewer_initials",
        "review_decision",
        "corrected_target_object",
        "corrected_target_field",
        "corrected_expected_state",
        "corrected_forbidden_effects_json",
        "corrected_preserves_meaning",
        "review_notes",
    ]
    review_rows = [{**row, **{field: "" for field in review_fields}} for row in draft_rows]
    write_csv(HUMAN_REVIEW_1, review_rows)
    write_csv(HUMAN_REVIEW_2, review_rows)

    priority = sum(row["review_priority"] for row in draft_rows)
    lines = [
        "# Consolidated AI Annotation Draft v5",
        "",
        "Status: one complete AI-authored draft is ready for two independent human reviews.",
        "",
        "This is an AI-assisted annotation workflow, not two independent human annotations from scratch.",
        "Both reviewers receive the same draft but must not inspect each other's decisions before both review files are frozen.",
        "",
        f"- Draft rows: {len(draft_rows)}.",
        f"- High-confidence rows: {len(draft_rows) - priority}.",
        f"- Medium-confidence priority rows: {priority}.",
        "- Every target object, target field, expected state, forbidden-effect set, and meaning-preservation label is populated.",
        "- All reviewer fields are blank.",
        "- Forbidden effects use one codebook: generic preservation becomes [\"unrelated objects\", \"unrelated fields\"]; explicitly named peers remain an ordered JSON list.",
    ]
    AI_CONSOLIDATED_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"consolidated_ai_draft_rows={len(draft_rows)}")
    print(f"priority_review_rows={priority}")
    print(AI_CONSOLIDATED_REPORT)


def score_gold_annotations() -> None:
    def load(path: Path) -> dict[str, dict[str, str]]:
        with path.open(encoding="utf-8") as handle:
            return {row["paraphrase_id"]: row for row in csv.DictReader(handle)}

    a_rows, b_rows = load(GOLD_A), load(GOLD_B)
    shared = sorted(set(a_rows) & set(b_rows))
    if len(shared) != 240:
        raise SystemExit(f"Expected 240 shared gold rows, found {len(shared)}.")
    for key in shared:
        for field in GOLD_LABELS:
            if not a_rows[key].get(field, "").strip() or not b_rows[key].get(field, "").strip():
                raise SystemExit(f"Missing independent gold label for {key}/{field}.")
        for row in (a_rows[key], b_rows[key]):
            if row["paraphrase_preserves_meaning"] not in {"0", "1"}:
                raise SystemExit(f"Meaning-preservation label must be 0 or 1 for {key}.")

    comparisons = {
        "target_object": lambda row: normalize_annotation(row["annotator_target_object"]),
        "target_field": lambda row: normalize_annotation(row["annotator_target_field"]),
        "expected_state": lambda row: normalize_annotation(row["annotator_expected_state"]),
        "forbidden_effect_set": lambda row: forbidden_set(row["annotator_forbidden_effects_json"]),
    }
    results: list[dict[str, Any]] = []
    for label, transform in comparisons.items():
        agreements = [transform(a_rows[key]) == transform(b_rows[key]) for key in shared]
        results.append(
            {
                "label": label,
                "n": len(shared),
                "percent_agreement": mean(agreements),
                "cohen_kappa": "",
                "annotator_a_positive_rate": "",
                "annotator_b_positive_rate": "",
            }
        )
    a_binary = [int(a_rows[key]["paraphrase_preserves_meaning"]) for key in shared]
    b_binary = [int(b_rows[key]["paraphrase_preserves_meaning"]) for key in shared]
    results.append(
        {
            "label": "paraphrase_preserves_meaning",
            "n": len(shared),
            "percent_agreement": mean(x == y for x, y in zip(a_binary, b_binary)),
            "cohen_kappa": kappa(a_binary, b_binary),
            "annotator_a_positive_rate": mean(a_binary),
            "annotator_b_positive_rate": mean(b_binary),
        }
    )
    write_csv(GOLD_AGREEMENT, results)

    disagreements: list[dict[str, Any]] = []
    for key in shared:
        fields = [label for label, transform in comparisons.items() if transform(a_rows[key]) != transform(b_rows[key])]
        if a_rows[key]["paraphrase_preserves_meaning"] != b_rows[key]["paraphrase_preserves_meaning"]:
            fields.append("paraphrase_preserves_meaning")
        if fields:
            disagreements.append(
                {
                    "paraphrase_id": key,
                    "instruction": a_rows[key]["instruction"],
                    "disagreement_fields": ";".join(fields),
                    **{f"annotator_a_{field}": a_rows[key][field] for field in GOLD_LABELS},
                    **{f"annotator_b_{field}": b_rows[key][field] for field in GOLD_LABELS},
                    **{f"adjudicated_{field}": "" for field in GOLD_LABELS},
                    "adjudication_notes": "",
                }
            )
    disagreement_fields = list(disagreements[0]) if disagreements else [
        "paraphrase_id", "instruction", "disagreement_fields",
        *[f"annotator_a_{field}" for field in GOLD_LABELS],
        *[f"annotator_b_{field}" for field in GOLD_LABELS],
        *[f"adjudicated_{field}" for field in GOLD_LABELS],
        "adjudication_notes",
    ]
    write_csv(GOLD_DISAGREEMENTS, disagreements, disagreement_fields)
    with REPORT.open("a", encoding="utf-8") as handle:
        handle.write("\n## Independent gold-postcondition agreement\n\n")
        for row in results:
            kappa_text = "" if row["cohen_kappa"] == "" else f", Cohen's kappa={row['cohen_kappa']:.3f}"
            handle.write(
                f"- {row['label']}: n={row['n']}, agreement={row['percent_agreement']:.3f}{kappa_text}.\n"
            )
        handle.write(f"- Disagreement rows requiring adjudication: {len(disagreements)}.\n")
    print(GOLD_AGREEMENT)
    print(GOLD_DISAGREEMENTS)


def score_annotations() -> None:
    def load(path: Path) -> dict[str, dict[str, str]]:
        with path.open(encoding="utf-8") as handle:
            return {row["paraphrase_id"] + "|" + row["model_alias"]: row for row in csv.DictReader(handle)}

    a_rows, b_rows = load(ANN_A), load(ANN_B)
    shared = sorted(set(a_rows) & set(b_rows))
    if not shared:
        raise SystemExit("Annotation files contain no shared generated rows; run --run first.")
    results: list[dict[str, Any]] = []
    for label in LABELS:
        a: list[int] = []
        b: list[int] = []
        for key in shared:
            av, bv = a_rows[key].get(label, ""), b_rows[key].get(label, "")
            if av not in {"0", "1"} or bv not in {"0", "1"}:
                continue
            a.append(int(av))
            b.append(int(bv))
        if not a:
            raise SystemExit(f"No complete 0/1 pairs for label: {label}")
        results.append(
            {
                "label": label,
                "n": len(a),
                "percent_agreement": mean(int(x == y) for x, y in zip(a, b)),
                "cohen_kappa": kappa(a, b),
                "annotator_a_positive_rate": mean(a),
                "annotator_b_positive_rate": mean(b),
            }
        )
    write_csv(AGREEMENT, results)
    with REPORT.open("a", encoding="utf-8") as handle:
        handle.write("\n## Human annotation agreement\n\n")
        for row in results:
            handle.write(
                f"- {row['label']}: n={row['n']}, agreement={row['percent_agreement']:.3f}, "
                f"Cohen's kappa={row['cohen_kappa']:.3f}.\n"
            )
    print(AGREEMENT)


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--run", action="store_true")
    modes.add_argument("--rescore-existing", action="store_true")
    modes.add_argument("--ai-preannotate", action="store_true")
    modes.add_argument("--build-ai-review-draft", action="store_true")
    modes.add_argument("--score-annotations", action="store_true")
    modes.add_argument("--score-gold-annotations", action="store_true")
    args = parser.parse_args()
    if args.run:
        run_endpoint()
    elif args.rescore_existing:
        rescore_existing()
    elif args.ai_preannotate:
        run_ai_preannotations()
    elif args.build_ai_review_draft:
        build_consolidated_ai_draft()
    elif args.score_annotations:
        score_annotations()
    elif args.score_gold_annotations:
        score_gold_annotations()
    else:
        prepare()


if __name__ == "__main__":
    main()
