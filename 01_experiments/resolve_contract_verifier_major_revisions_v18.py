#!/usr/bin/env python3
"""Resolve the four Major Revise findings from the blinded contract/verifier audit.

This supplemental verifier leaves the frozen v6 benchmark/results unchanged and
re-verifies only B08, B10, B11, and B12. Outputs contain no model/policy/outcome
information and are suitable for blinded human re-audit evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from run_ase_autonomous_repair_v6 import (
    build_tasks,
    semantic_changed_paths,
    validate_target,
    write_repository,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
JSON_OUT = OUT / "contract_verifier_major_revision_evidence_v18.json"
MD_OUT = OUT / "contract_verifier_major_revision_report_v18.md"

AUDIT_TO_TASK = {
    "B08": "repo_23_deploy_permissions",
    "B10": "repo_31_stable_deduplication",
    "B11": "repo_35_duration_parser",
    "B12": "repo_39_configuration_precedence",
}

BEHAVIORAL_PREDICATES = {
    "B08": (
        "Every .github/workflows/deploy_*.yml file has top-level permissions.contents=read; "
        "test.yml, lint.yml, and every path under examples/ remain semantically unchanged; "
        "no other repository path changes."
    ),
    "B10": (
        "For any finite input sequence, unique(items) returns exactly one representative of each "
        "equality-equivalent value, choosing the first occurrence and preserving the order of those "
        "first occurrences; it works for hashable and unhashable values and does not modify tests."
    ),
    "B11": (
        "parse_duration accepts exactly strings consisting of a non-negative base-10 integer followed "
        "immediately by ms, s, or m; it returns the corresponding millisecond count and raises ValueError "
        "for negative or malformed inputs."
    ),
    "B12": (
        "resolve(defaults, file_values, env_values) returns a new mapping with precedence defaults < file "
        "< environment; None-valued overrides are ignored, keys absent from lower-priority mappings may be "
        "introduced by higher-priority mappings, and none of the three input mappings is mutated."
    ),
}

HIDDEN_CHECKS = {
    "repo_31_stable_deduplication": """
from src.dedupe import unique
assert unique([1, 1, 2, 1, 3, 2]) == [1, 2, 3]
assert unique(['b', 'a', 'b', 'c', 'a']) == ['b', 'a', 'c']
assert unique([]) == []
assert unique(['only']) == ['only']
assert unique([[1], [1], [2], [1]]) == [[1], [2]]
assert unique([{'x': 1}, {'x': 1}, {'x': 2}]) == [{'x': 1}, {'x': 2}]
""".strip(),
    "repo_35_duration_parser": """
from src.duration import parse_duration
for text, expected in {
    '0ms': 0, '0s': 0, '0m': 0, '250ms': 250, '12s': 12000, '34m': 2040000,
}.items():
    assert parse_duration(text) == expected, (text, parse_duration(text), expected)
for bad in ['-1s', '-10ms', '1.5s', '10', 'ms', '', '1h', ' 1s', '1s ', '+1s']:
    try:
        parse_duration(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f'{bad!r} must raise ValueError')
""".strip(),
    "repo_39_configuration_precedence": """
from copy import deepcopy
from src.precedence import resolve

def check(defaults, file_values, env_values, expected):
    originals = (deepcopy(defaults), deepcopy(file_values), deepcopy(env_values))
    actual = resolve(defaults, file_values, env_values)
    assert actual == expected, (actual, expected)
    assert defaults == originals[0], 'defaults mutated'
    assert file_values == originals[1], 'file_values mutated'
    assert env_values == originals[2], 'env_values mutated'

check({'x': 0}, {'x': 1}, {'x': 2}, {'x': 2})
check({'x': 0, 'y': 9}, {'x': 1}, {}, {'x': 1, 'y': 9})
check({'x': 0}, {'x': None}, {}, {'x': 0})
check({'x': 0}, {'x': 1}, {'x': None}, {'x': 1})
check({'x': 0}, {}, {'x': None}, {'x': 0})
check({}, {'file_only': 1}, {'env_only': 2}, {'file_only': 1, 'env_only': 2})
""".strip(),
}

COVERAGE_MANIFEST = {
    "B08": [
        "Enumerate and SHA-256 every frozen examples/ file.",
        "Compute a deterministic examples/ tree hash.",
        "Gold state satisfies target with no residue.",
        "Mutation of an existing examples/ file is detected as residue.",
        "Creation of a new examples/ file is detected as residue.",
    ],
    "B10": [
        "ordinary repeated hashable values", "stable first-occurrence order", "empty input",
        "single-element input", "unhashable list values", "unhashable dict values",
    ],
    "B11": [
        "ms, s, and m units", "zero values", "multi-digit values", "negative values",
        "malformed formats", "ValueError failure type",
    ],
    "B12": [
        "default < file precedence", "file < environment precedence", "None ignored at file layer",
        "None ignored at environment layer", "missing/new keys",
        "non-mutation of defaults, file_values, and env_values",
    ],
}

MUTANTS = {
    "repo_31_stable_deduplication": [
        ("hash_only_dedup", "def unique(items):\n    return list(dict.fromkeys(items))\n"),
        ("sorts_instead_of_stable_order", "def unique(items):\n    return sorted(set(items))\n"),
    ],
    "repo_35_duration_parser": [
        ("rejects_zero_and_strips_whitespace", """import re

def parse_duration(text):
    text = text.strip()
    m = re.fullmatch(r'([1-9]\\d*)(ms|s|m)', text)
    if not m:
        raise ValueError('invalid')
    n, u = int(m.group(1)), m.group(2)
    return n * {'ms':1,'s':1000,'m':60000}[u]
"""),
    ],
    "repo_39_configuration_precedence": [
        ("env_none_overwrites_file_and_mutates_defaults", """def resolve(defaults, file_values, env_values):
    defaults.update({k:v for k,v in file_values.items() if v is not None})
    defaults.update(env_values)
    return defaults
"""),
        ("drops_new_keys", """def resolve(defaults, file_values, env_values):
    result = dict(defaults)
    for key in list(result):
        if file_values.get(key) is not None:
            result[key] = file_values[key]
        if env_values.get(key) is not None:
            result[key] = env_values[key]
    return result
"""),
    ],
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tree_hash(entries: list[dict[str, str]]) -> str:
    payload = "".join(f"{row['path']}\0{row['sha256']}\n" for row in sorted(entries, key=lambda r: r["path"]))
    return sha256_text(payload)


def run_code(root: Path, code: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["python3", "-c", code], cwd=root, capture_output=True, text=True, timeout=20,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    detail = (result.stdout + "\n" + result.stderr).strip()[-4000:]
    return result.returncode == 0, detail


def validate_v18(task: Any, root: Path, state: dict[str, str]) -> tuple[bool, str]:
    base_ok, base_detail = validate_target(task, root, state)
    if not base_ok:
        return False, base_detail
    hidden = HIDDEN_CHECKS.get(task.task_id)
    if hidden:
        ok, detail = run_code(root, hidden)
        if not ok:
            return False, "v18 hidden specification check failed:\n" + detail
    return True, base_detail


def state_result(task: Any, state: dict[str, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="csdvr_contract_v18_") as tmp:
        root = Path(tmp)
        write_repository(root, state)
        target_ok, detail = validate_v18(task, root, state)
        unexpected = sorted(semantic_changed_paths(task.before, state) - set(task.intended_paths))
        residue = bool(unexpected)
        return {
            "target_satisfied": target_ok,
            "residue": residue,
            "success": bool(target_ok and not residue),
            "unexpected_paths": unexpected,
            "validator_detail": detail,
        }


def mutant_rejected(task: Any, label: str, source: str) -> dict[str, Any]:
    path = next(iter(task.intended_paths))
    state = deepcopy(task.gold)
    state[path] = source
    result = state_result(task, state)
    return {"label": label, "rejected": not result["success"], "result": result}


def b08_evidence(task: Any) -> dict[str, Any]:
    examples = [
        {"path": path, "sha256": sha256_text(task.before[path])}
        for path in sorted(task.before) if path == "examples" or path.startswith("examples/")
    ]
    existing_mutation = deepcopy(task.gold)
    existing_path = examples[0]["path"]
    existing_mutation[existing_path] = "name: changed_example\njobs: {}\nforbidden: true\n"
    existing_result = state_result(task, existing_mutation)
    new_file_mutation = deepcopy(task.gold)
    new_file_mutation["examples/unexpected_added.yml"] = "forbidden: true\n"
    new_file_result = state_result(task, new_file_mutation)
    return {
        "examples_manifest": examples,
        "examples_tree_sha256": tree_hash(examples),
        "manifest_count": len(examples),
        "existing_file_mutation_detected": bool(existing_result["residue"] and not existing_result["success"]),
        "new_file_creation_detected": bool(new_file_result["residue"] and not new_file_result["success"]),
        "existing_file_mutation_result": existing_result,
        "new_file_creation_result": new_file_result,
    }


def main() -> None:
    tasks = {task.task_id: task for task in build_tasks()}
    evidence: dict[str, Any] = {
        "version": "v18",
        "blinding": "No model identity, policy, success-rate, failure-log, residue-log, or outcome data used.",
        "audit_to_task": AUDIT_TO_TASK,
        "behavioral_predicates": BEHAVIORAL_PREDICATES,
        "coverage_manifest": COVERAGE_MANIFEST,
        "tasks": {},
    }
    all_pass = True
    for audit_id, task_id in AUDIT_TO_TASK.items():
        task = tasks[task_id]
        before_result = state_result(task, task.before)
        gold_result = state_result(task, task.gold)
        item: dict[str, Any] = {"task_id": task_id, "before_rerun": before_result, "gold_rerun": gold_result}
        checks = [not before_result["success"], gold_result["success"]]
        if audit_id == "B08":
            item.update(b08_evidence(task))
            checks.extend([
                item["existing_file_mutation_detected"], item["new_file_creation_detected"], item["manifest_count"] >= 1,
            ])
        else:
            mutants = [mutant_rejected(task, label, source) for label, source in MUTANTS[task_id]]
            item["mutants"] = mutants
            checks.extend(m["rejected"] for m in mutants)
        item["local_rerun_pass"] = bool(all(checks))
        all_pass = all_pass and item["local_rerun_pass"]
        evidence["tasks"][audit_id] = item

    evidence["summary"] = {
        "tasks_checked": 4,
        "tasks_passing_local_rerun": sum(int(v["local_rerun_pass"]) for v in evidence["tasks"].values()),
        "all_four_pass_local_rerun": all_pass,
        "formal_human_reaudit_status": "PENDING",
        "main_84000_run_status": "NOT_RERUN",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Contract / Verifier Major-Revision Resolution v18", "",
        "> Scope: B08, B10, B11, B12 only. This is deterministic pre-reaudit evidence, not a human review.", "",
        "## Summary", "",
        f"- Local task/verifier reruns passing: **{evidence['summary']['tasks_passing_local_rerun']}/4**",
        "- Full 84,000-run experiment rerun: **NOT_RERUN**",
        "- Formal independent human re-audit: **PENDING**",
        "- Original v6 benchmark/results remain frozen and unmodified.", "",
        "## Revised behavioral predicates", "",
    ]
    for audit_id in ["B08", "B10", "B11", "B12"]:
        lines += [f"### {audit_id}", "", BEHAVIORAL_PREDICATES[audit_id], "", "Verifier coverage:"]
        lines += [f"- {case}" for case in COVERAGE_MANIFEST[audit_id]]
        lines.append("")
    b08 = evidence["tasks"]["B08"]
    lines += ["## B08 frozen examples/ manifest", "", "| Path | SHA-256 |", "|---|---|"]
    for row in b08["examples_manifest"]:
        lines.append(f"| `{row['path']}` | `{row['sha256']}` |")
    lines += [
        "", f"Frozen subtree hash: `{b08['examples_tree_sha256']}`", "",
        f"Existing-file mutation detected as residue: **{b08['existing_file_mutation_detected']}**",
        f"New-file creation under examples/ detected as residue: **{b08['new_file_creation_detected']}**", "",
        "## Local rerun results", "",
        "| Audit ID | Frozen task ID | Broken baseline rejected | Gold accepted | Adversarial verifier probes rejected | Local result |",
        "|---|---|---:|---:|---:|---|",
    ]
    for audit_id in ["B08", "B10", "B11", "B12"]:
        item = evidence["tasks"][audit_id]
        probes = (
            item["existing_file_mutation_detected"] and item["new_file_creation_detected"]
            if audit_id == "B08" else all(m["rejected"] for m in item["mutants"])
        )
        lines.append(
            f"| {audit_id} | `{item['task_id']}` | {not item['before_rerun']['success']} | "
            f"{item['gold_rerun']['success']} | {probes} | {'PASS' if item['local_rerun_pass'] else 'FAIL'} |"
        )
    lines += [
        "", "## Interpretation", "",
        "These checks close the evidence/coverage gaps identified in the simulated v17 audit without rewriting the original v6 experiment history. They do **not** by themselves authorize the paper to claim a completed independent human audit. A genuinely independent human reviewer must re-review B08/B10/B11/B12 and freeze the new ratings before seeing model/policy/outcome data.",
        "", "The 84,000-run benchmark is not rerun here. If a trajectory-level replay under the strengthened verifier changes success, residue, or restoration-scope classification, the corresponding aggregate/numeric audit must then be updated.", "",
    ]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Local rerun: {evidence['summary']['tasks_passing_local_rerun']}/4 PASS")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    print(f"Wrote {MD_OUT.relative_to(ROOT)}")
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
