#!/usr/bin/env python3
"""Six-task, same-command, same-contract supplementary replay on native YoloFS."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import io
import time
import tempfile
import os


HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks_opaque"
ENGINE_PATH = HERE / "recovery_engine.py"
PROTOCOL_PATH = HERE / "yolofs_extended_matched_replay_protocol_20261007_v2_gitblob.json"
INPUT_MANIFEST_PATH = HERE / "yolofs_extended_task_inputs_gitblob_manifest_20261007.json"
OUTPUT = HERE / "yolofs_extended_matched_replay_20261007_v2_results.json"
TRIAL_ROOT = Path(os.environ.get("CSDVR_TRIAL_ROOT", str(Path(tempfile.gettempdir()) / "csdvr_yolofs_extended_matched_20261007_v2")))

HARNESS_FILES = {"yolofs.toml", "AGENTS.md", "CLAUDE.md", "GEMINI.md"}
HARNESS_DIRS = {".yolofs", ".claude", ".gemini", ".github"}
POLICIES = (
    "yolofs_travel_pre",
    "yolofs_commit_post",
    "yolofs_preventive_permissions",
    "csdvr_projected",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_engine():
    spec = importlib.util.spec_from_file_location("csdvr_recovery_engine", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import recovery engine: {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root: Path) -> dict[str, bytes]:
    state: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in HARNESS_DIRS for part in rel.parts) or rel.as_posix() in HARNESS_FILES:
            continue
        if path.is_file():
            state[rel.as_posix()] = path.read_bytes()
    return state


def manifest(state: dict[str, bytes]) -> dict[str, str]:
    return {name: sha256(value) for name, value in sorted(state.items())}


def verify_inputs(input_manifest: dict) -> None:
    for task in input_manifest["tasks"]:
        root = TASKS / task["task"]
        if not root.is_dir():
            raise FileNotFoundError(root)
        expected = {item["path"]: item["sha256"] for item in task["files"]}
        actual = {
            path.relative_to(root).as_posix(): file_sha256(path)
            for path in sorted(root.rglob("*")) if path.is_file()
        }
        if actual != expected:
            raise ValueError(f"input fixture manifest mismatch for {task['task']}")


def prepare_case(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    for script in destination.rglob("*.sh"):
        script.write_bytes(script.read_bytes().replace(b"\r\n", b"\n"))


def materialize(root: Path, state: dict[str, bytes]) -> None:
    current = snapshot(root)
    for name in current.keys() - state.keys():
        (root / name).unlink()
    for name, content in state.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def cli(args: list[str], cwd: Path, label: str, allow_failure: bool = False) -> dict:
    started = time.perf_counter()
    completed = subprocess.run(
        ["yolo", *args], cwd=cwd, text=True, capture_output=True, timeout=180, check=False
    )
    record = {
        "label": label,
        "argv": ["yolo", *args],
        "return_code": completed.returncode,
        "elapsed_seconds": time.perf_counter() - started,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.returncode != 0 and not allow_failure:
        raise RuntimeError(json.dumps(record, ensure_ascii=False, indent=2))
    return record


def score_target(task: str, state: dict[str, bytes], base: dict[str, bytes], oracle: dict) -> tuple[bool, dict]:
    if "required_absent" in oracle:
        paths = oracle["required_absent"]
        passed = all(path not in state for path in paths)
        return passed, {"required_absent": paths, "all_absent": passed}
    if "byte_equal_pairs" in oracle:
        pairs = oracle["byte_equal_pairs"]
        detail = {
            dst: {"present": dst in state, "matches_source": dst in state and src in base and state[dst] == base[src]}
            for src, dst in pairs
        }
        return all(item["matches_source"] for item in detail.values()), {"outputs": detail}
    if "archive_file_members" in oracle:
        archive = state.get("backups/backup.tar.gz")
        if archive is None:
            return False, {"archive_present": False, "members": {}}
        expected = set(oracle["archive_file_members"])
        members: dict[str, bytes] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                for item in tar.getmembers():
                    if item.isfile():
                        name = item.name.removeprefix("./").lstrip("/")
                        extracted = tar.extractfile(item)
                        if extracted is not None:
                            members[name] = extracted.read()
        except (tarfile.TarError, OSError) as exc:
            return False, {"archive_present": True, "archive_valid": False, "error": str(exc)}
        exact_names = set(members) == expected if oracle.get("no_other_file_members") else expected.issubset(members)
        bytes_match = all(path in base and members.get(path) == base[path] for path in expected)
        passed = exact_names and (bytes_match if oracle.get("member_bytes_equal_source") else True)
        return passed, {
            "archive_present": True,
            "archive_sha256": sha256(archive),
            "archive_valid": True,
            "file_members": sorted(members),
            "exact_expected_file_members": exact_names,
            "all_member_bytes_match_source": bytes_match,
        }
    if "exact_contents_utf8" in oracle:
        expected = {path: text.encode("utf-8") for path, text in oracle["exact_contents_utf8"].items()}
        detail = {path: path in state and state[path] == value for path, value in expected.items()}
        return all(detail.values()), {"exact_content_matches": detail}
    raise ValueError(f"unknown target oracle for {task}")


def integrity_preserved(base: dict[str, bytes], candidate: dict[str, bytes], allowed: set[str]) -> bool:
    before = {path: value for path, value in base.items() if path not in allowed}
    after = {path: value for path, value in candidate.items() if path not in allowed}
    return before == after


def main() -> None:
    if not TASKS.is_dir() or not ENGINE_PATH.is_file():
        raise SystemExit(f"missing experiment inputs under {HERE}")
    if TRIAL_ROOT.exists():
        raise SystemExit(f"refusing to overwrite trial directory: {TRIAL_ROOT}")
    protocol = load_json(PROTOCOL_PATH)
    input_manifest = load_json(INPUT_MANIFEST_PATH)
    if protocol["status"] != "FROZEN_BEFORE_RUN":
        raise ValueError("protocol was not frozen before the experiment")
    verify_inputs(input_manifest)
    engine = load_engine()
    case_specs = {item["task"]: item for item in protocol["cases"]}
    if set(case_specs) != set(protocol["design"]["execution_order"]):
        raise ValueError("protocol case list/order mismatch")

    TRIAL_ROOT.mkdir(parents=True)
    results = []
    try:
        for task, arm_order in protocol["design"]["execution_order"].items():
            spec = case_specs[task]
            source = TASKS / task
            allowed = set(spec["allowed_paths"])
            arm_results = {}
            baseline_manifest = None
            baseline_state = None
            observed_for_archive = None
            for policy in arm_order:
                if policy not in POLICIES:
                    raise ValueError(f"unknown arm {policy}")
                work = TRIAL_ROOT / f"{task}__{policy}"
                prepare_case(source, work)
                base = snapshot(work)
                current_manifest = manifest(base)
                if baseline_manifest is None:
                    baseline_manifest = current_manifest
                    baseline_state = base
                elif current_manifest != baseline_manifest:
                    raise RuntimeError(f"baseline hash mismatch across arms for {task}")

                commands = [cli(["init"], work, "init")]
                if policy == "yolofs_preventive_permissions":
                    roots = sorted({path.split("/", 1)[0] for path in allowed})
                    for name in roots:
                        (work / name).mkdir(parents=True, exist_ok=True)
                    commands.append(cli(["rule", "read-only", "."], work, "protect_project_root"))
                    for name in roots:
                        commands.append(cli(["rule", "allow", name], work, f"allow_target_root:{name}"))

                run = cli(
                    ["run", "--", *spec["command"]], work, "task_command",
                    allow_failure=(policy == "yolofs_preventive_permissions"),
                )
                commands.append(run)
                commands.append(cli(["timeline"], work, "timeline_after_run"))

                if policy == "yolofs_travel_pre":
                    commands.append(cli(["travel", "0"], work, "native_travel_to_base"))
                    commands.append(cli(["commit"], work, "commit_travelled_state"))
                    commands.append(cli(["unmount"], work, "unmount"))
                    candidate = snapshot(work)
                else:
                    commands.append(cli(["commit"], work, "native_commit_tip"))
                    commands.append(cli(["unmount"], work, "unmount"))
                    observed = snapshot(work)
                    if policy == "yolofs_commit_post":
                        observed_for_archive = observed
                    if policy in ("yolofs_commit_post", "yolofs_preventive_permissions"):
                        candidate = observed
                    else:
                        candidate = engine.project(base, observed, allowed)
                        materialize(work, candidate)
                        candidate = snapshot(work)

                target_ok, target_details = score_target(task, candidate, base, spec["oracle"])
                intact = integrity_preserved(base, candidate, allowed)
                arm_results[policy] = {
                    "target_pass": target_ok,
                    "target_details": target_details,
                    "integrity_preserved": intact,
                    "joint_pass": target_ok and intact,
                    "command_exit_code": run["return_code"],
                    "command_exit_zero": run["return_code"] == 0,
                    "final_file_count": len(candidate),
                    "final_sha256_by_path": manifest(candidate),
                }

            if baseline_state is None or observed_for_archive is None:
                raise RuntimeError(f"missing state evidence for {task}")
            results.append({
                "task": task,
                "command": spec["command"],
                "allowed_paths": sorted(allowed),
                "baseline_sha256_by_path": baseline_manifest,
                "execution_order": arm_order,
                "arms": arm_results,
            })
    finally:
        shutil.rmtree(TRIAL_ROOT)

    aggregate = {}
    for policy in POLICIES:
        rows = [row["arms"][policy] for row in results]
        aggregate[policy] = {
            "target_pass": sum(row["target_pass"] for row in rows),
            "integrity_preserved": sum(row["integrity_preserved"] for row in rows),
            "joint_pass": sum(row["joint_pass"] for row in rows),
            "command_exit_zero": sum(row["command_exit_zero"] for row in rows),
            "denominator": len(rows),
        }
    report = {
        "study": protocol["study"],
        "protocol_sha256": file_sha256(PROTOCOL_PATH),
        "input_manifest_sha256": file_sha256(INPUT_MANIFEST_PATH),
        "task_repository_commit": input_manifest["repository_commit"],
        "yolofs_source_commit": "8848c243ba28ff91432c1da868671d6ed8910ed6",
        "model_or_api_calls": 0,
        "official_yolofs_benchmark_score": False,
        "arms": {policy: protocol["arms"][policy] for policy in POLICIES},
        "joint_outcome": protocol["joint_outcome"],
        "aggregate": aggregate,
        "cases": results,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
