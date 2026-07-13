#!/usr/bin/env python3
"""Build the semantically auditable subset of the legacy v4 endpoint run.

The original v4 oracle exactly checked single-object field updates, deletions,
table-cell updates, and workflow-step completion. It did not fully check file
content provenance or all fields of created form records. Because only response
hashes were retained, those excluded outcomes cannot be recomputed offline.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
RAW = OUT / "llm_agent_validation_raw_v4.csv"
JUDGE = OUT / "llm_judge_consistency_v4.csv"
AUDITED_RAW = OUT / "llm_agent_validation_audited_subset_v4.csv"
AUDITED_SUMMARY = OUT / "llm_agent_validation_audited_subset_summary_v4.csv"
AUDITED_JUDGE = OUT / "llm_judge_consistency_audited_subset_v4.csv"
AUDIT_NOTE = OUT / "llm_agent_validation_audit_note_v4.md"

sys.path.insert(0, str(ROOT / "01_experiments"))
from run_llm_agent_validation_v4 import build_tasks  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path.name}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def as_float(value: Any) -> float:
    text = str(value).strip().lower()
    if text in {"true", "yes"}:
        return 1.0
    if text in {"false", "no", "", "nan"}:
        return 0.0
    return float(text)


def main() -> None:
    tasks = build_tasks()
    eligible = {
        task.task_id
        for task in tasks
        if task.domain in {"web_form", "table", "workflow_micro"} and task.op != "create"
    }
    excluded = {task.task_id for task in tasks} - eligible
    raw = read_csv(RAW)
    audited = [row | {"audit_scope": "single_object_exact_field"} for row in raw if row["task_id"] in eligible]
    expected = len(eligible) * 2 * 6 * 2
    if len(audited) != expected:
        raise AssertionError(f"Expected {expected} audited endpoint rows, found {len(audited)}")

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in audited:
        grouped[(row["model"], row["policy"])].append(row)
    summary: list[dict[str, Any]] = []
    for (model, policy), rows in sorted(grouped.items()):
        summary.append(
            {
                "model": model,
                "policy": policy,
                "runs": len(rows),
                "success": f"{mean(as_float(row['success']) for row in rows):.4f}",
                "residue": f"{mean(as_float(row['residue']) for row in rows):.4f}",
                "invalid_action_rate": f"{mean(as_float(row['invalid_json']) for row in rows):.4f}",
                "invalid_judge_rate": f"{mean(as_float(row['invalid_judge_json']) > 0 for row in rows):.4f}",
                "judge_false_success": f"{mean(as_float(row['judge_false_success']) for row in rows):.4f}",
                "judge_side_effect_recall": f"{mean(as_float(row['judge_side_effect_recall']) for row in rows):.4f}",
                "token_cost": f"{mean(as_float(row['token_cost']) for row in rows):.2f}",
            }
        )

    judge_rows = read_csv(JUDGE)
    audited_judge = [row | {"audit_scope": "single_object_exact_field"} for row in judge_rows if row["task_id"] in eligible]
    expected_judge = len(eligible) * 2 * 3 * 2
    if len(audited_judge) != expected_judge:
        raise AssertionError(f"Expected {expected_judge} audited judge rows, found {len(audited_judge)}")

    write_csv(AUDITED_RAW, audited)
    write_csv(AUDITED_SUMMARY, summary)
    write_csv(AUDITED_JUDGE, audited_judge)

    note = [
        "# LLM-Agent v4 Semantic-Oracle Audit",
        "",
        "Status: PARTIAL DATA RETENTION AFTER PRE-SUBMISSION ORACLE AUDIT",
        "",
        f"Original endpoint rows: {len(raw)}.",
        f"Audited efficacy rows retained: {len(audited)} across {len(eligible)} tasks.",
        f"Audited judge-consistency rows retained: {len(audited_judge)}.",
        "",
        "## Inclusion Rule",
        "",
        "Retain only operations whose legacy oracle checked the exact intended object and field (or exact deletion/completion condition) and whose one-action schema could not modify a second field on the same object: web-form edit/status/delete, table update_cell, and workflow complete_step.",
        "",
        "## Exclusion Rule",
        "",
        "Exclude all file tasks because the legacy snapshot stored content hashes while the oracle checked path existence rather than content provenance. Exclude web-form create tasks because the legacy oracle checked record existence rather than all requested fields. Raw model responses were retained only as hashes, so excluded outcomes cannot be recomputed without a new endpoint run.",
        "",
        "## Reproduction Status",
        "",
        "The corrected runner now uses semantic-state-v2, exact expected-state construction, and content-preserving rollback. A future endpoint rerun may replace this audited subset with a complete corrected result; until then, only the audited subset is eligible for manuscript efficacy claims.",
        "",
        "Excluded task IDs: " + ", ".join(sorted(excluded)),
    ]
    AUDIT_NOTE.write_text("\n".join(note) + "\n", encoding="utf-8")
    print(f"audited_endpoint_rows={len(audited)}")
    print(f"audited_judge_rows={len(audited_judge)}")
    print(AUDIT_NOTE)


if __name__ == "__main__":
    main()
