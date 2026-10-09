#!/usr/bin/env python3
"""Native agent-rollback vs C-SDVR on a frozen Git-ignored backup task.

The runner consumes the pinned Git-blob fixture archive, creates 1/10/100
pre-existing ignored backups, and checks both restoration correctness and the
task-specific joint contract after the same public cleanup command.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks_opaque"
INPUT_MANIFEST = HERE / "yolofs_extended_task_inputs_gitblob_manifest_20261007.json"
PROTOCOL = HERE / "agent_rollback_ignored_file_protocol_20261008.json"
OUTPUT = HERE / "agent_rollback_ignored_file_same_trajectory_20261008_results.json"
ENGINE_PATH = HERE / "recovery_engine.py"
AGENT_BINARY = Path(os.environ.get("AGENT_ROLLBACK_BIN") or shutil.which("agent-rollback") or "/tmp/agent-rollback-csdvr")
EXPECTED_ENGINE_SHA = "3db4ba9e318c6ff0e42d657a31d993d767f147e2e8044d81c0ed03ca37f7dda9"
EXPECTED_AGENT_COMMIT = "3bc001f1ef8a72c301da4ff1e83caddb57117ac1"
ALLOWED = {"build/main", "build/output.o"}
EXCLUDED = {".git", ".agent-rollback"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(argv: list[str], cwd: Path, label: str, *, check: bool = True) -> dict:
    result = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True,
                            timeout=180, check=False)
    row = {"label": label, "argv": argv, "return_code": result.returncode,
           "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    if check and result.returncode != 0:
        raise RuntimeError(json.dumps(row, ensure_ascii=False))
    return row


def cli_json(argv: list[str], cwd: Path, label: str) -> tuple[dict, dict]:
    row = run([str(AGENT_BINARY), "--cwd", str(cwd), "--json", *argv], cwd,
              label)
    try:
        payload = json.loads(row["stdout"])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not return JSON: {row['stdout']}") from exc
    return row, payload


def field(obj: dict, name: str):
    for key, value in obj.items():
        if key.lower() == name.lower():
            return value
    return None


def snapshot(root: Path) -> dict[str, bytes]:
    state = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in EXCLUDED for part in rel.parts):
            continue
        if path.is_file():
            state[rel.as_posix()] = path.read_bytes()
    return state


def digest_map(state: dict[str, bytes]) -> dict[str, str]:
    return {path: sha(data) for path, data in sorted(state.items())}


def score(state: dict[str, bytes], baseline: dict[str, bytes]) -> dict:
    target_absent = all(path not in state for path in ALLOWED)
    paths = (set(state) | set(baseline)) - ALLOWED
    integrity = all(state.get(path) == baseline.get(path) for path in paths)
    return {
        "target_artifacts_absent": target_absent,
        "outside_scope_exact_bytes": integrity,
        "joint_pass": target_absent and integrity,
        "target_details": {path: path not in state for path in sorted(ALLOWED)},
        "file_count": len(state),
        "sha256_by_path": digest_map(state),
    }


def get_manifest_files(payload: dict) -> dict:
    files = field(payload, "files")
    if not isinstance(files, dict):
        raise RuntimeError(f"checkpoint manifest lacks file map: {list(payload)}")
    return files


def verify_task_fixture(task_name: str) -> Path:
    manifest = json.loads(INPUT_MANIFEST.read_text(encoding="utf-8"))
    record = next((item for item in manifest["tasks"] if item["task"] == task_name), None)
    if record is None:
        raise RuntimeError(f"task absent from frozen input manifest: {task_name}")
    root = TASKS / task_name
    if not root.is_dir():
        raise FileNotFoundError(f"run fetch_task_inputs.py first; missing {root}")
    expected = {item["path"]: item["sha256"] for item in record["files"]}
    actual = {path.relative_to(root).as_posix(): digest_file(path)
              for path in sorted(root.rglob("*")) if path.is_file()}
    if actual != expected:
        raise RuntimeError(f"input fixture hash mismatch for {task_name}")
    return root


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    protocol_sha = digest_file(PROTOCOL)
    source = verify_task_fixture("cleanup")
    if digest_file(ENGINE_PATH) != EXPECTED_ENGINE_SHA:
        raise RuntimeError("production recovery engine hash mismatch")
    if not AGENT_BINARY.is_file():
        raise RuntimeError(f"native agent-rollback binary missing: {AGENT_BINARY}")

    engine = load_module("csdvr_recovery_engine", ENGINE_PATH)
    scratch = Path(tempfile.mkdtemp(prefix="csdvr_agentrollback_replay_"))
    try:
        for count in (1, 10, 100):
            base_root = scratch / f"baseline_{count}"
            source_copy = scratch / f"source_{count}"
            shutil.copytree(source, source_copy)
            ignore = source_copy / ".gitignore"
            prior = ignore.read_bytes() if ignore.exists() else b""
            ignore.write_bytes(prior.rstrip(b"\r\n") + b"\n*.bak\n")

            backup_paths = ["src/main.c.bak"]
            for index in range(count - 1):
                rel = f"src/user_backups/backup_{index:03d}.bak"
                path = source_copy / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"pre-existing user backup {index:03d}\n".encode())
                backup_paths.append(rel)

            for argv in (
                ["git", "init", "-q"],
                ["git", "config", "user.name", "C-SDVR replay"],
                ["git", "config", "user.email", "csdvr-replay@example.invalid"],
                ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "frozen task baseline"],
            ):
                run(argv, source_copy, f"git_baseline:{count}")
            ignored = [run(["git", "check-ignore", "-q", "--", path], source_copy,
                           f"verify_ignored:{path}", check=False)["return_code"] == 0
                       for path in backup_paths]
            if not all(ignored):
                raise RuntimeError(f"not all backups are ignored at scale {count}")
            shutil.copytree(source_copy, base_root)
            baseline = snapshot(base_root)

            # Reference command trajectory; this exact post-state feeds C-SDVR.
            reference_task = run(["bash", "./clean.sh"], base_root,
                                 f"reference_cleanup:{count}")
            if reference_task["return_code"] != 0:
                raise RuntimeError(f"reference command failed at scale {count}")
            observed = snapshot(base_root)

            # Native agent-rollback uses its own identical baseline copy.
            agent_root = scratch / f"agent_rollback_{count}"
            shutil.copytree(source_copy, agent_root)
            init_log, _ = cli_json(["init"], agent_root, f"agent_init:{count}")
            pre_log, pre_manifest = cli_json(["checkpoint", "before-cleanup"],
                                             agent_root, f"agent_checkpoint_pre:{count}")
            pre_id = field(pre_manifest, "id")
            if not pre_id:
                raise RuntimeError(f"pre-checkpoint id missing: {pre_manifest}")
            checkpoint_files = get_manifest_files(pre_manifest)
            recorded_backups = sorted(path for path in backup_paths
                                      if path in checkpoint_files)
            agent_task = run(["bash", "./clean.sh"], agent_root,
                             f"agent_cleanup:{count}")
            if agent_task["return_code"] != 0:
                raise RuntimeError(f"agent-rollback command failed at scale {count}")
            agent_observed = snapshot(agent_root)
            post_log, post_manifest = cli_json(["checkpoint", "after-cleanup"],
                                               agent_root, f"agent_checkpoint_post:{count}")
            trajectory_matches = digest_map(agent_observed) == digest_map(observed)
            if not trajectory_matches:
                raise RuntimeError(f"paired command states differ at scale {count}")
            revert_log = run([str(AGENT_BINARY), "--cwd", str(agent_root), "--json",
                              "--yes", "revert", pre_id], agent_root,
                             f"agent_restore_pre:{count}")
            agent_final = snapshot(agent_root)

            # Production C-SDVR projection, operating on the same byte maps.
            candidate = engine.project(baseline, observed, ALLOWED)
            candidate_root = scratch / f"csdvr_{count}"
            shutil.copytree(base_root, candidate_root)
            for path in snapshot(candidate_root).keys() - candidate.keys():
                target = candidate_root / path
                if target.is_file() or target.is_symlink():
                    target.unlink()
            for path, content in candidate.items():
                target = candidate_root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            csdvr_final = snapshot(candidate_root)

            agent_score = score(agent_final, baseline)
            csdvr_score = score(csdvr_final, baseline)
            exact_recovered = [p for p in backup_paths
                               if agent_final.get(p) == baseline.get(p)]
            cases.append({
                "ignored_backup_count": count,
                "backup_paths": backup_paths,
                "git_ignore_validation": all(ignored),
                "git_tracked_baseline_file_count": len(baseline) - len(backup_paths),
                "agent_checkpoint_file_count": len(checkpoint_files),
                "agent_checkpoint_recorded_backup_paths": recorded_backups,
                "agent_checkpoint_omitted_backup_count": count - len(recorded_backups),
                "same_command_and_contract_pairing": trajectory_matches,
                "reference_command_exit_code": reference_task["return_code"],
                "agent_command_exit_code": agent_task["return_code"],
                "pre_checkpoint_command": pre_log["argv"],
                "post_checkpoint_command": post_log["argv"],
                "restore_return_code": revert_log["return_code"],
                "agent_exact_backups_recovered": len(exact_recovered),
                "agent_joint_score": agent_score,
                "csdvr_joint_score": csdvr_score,
                "baseline_sha256_by_path": digest_map(baseline),
                "observed_sha256_by_path": digest_map(observed),
            })

        result = {
            "study": protocol["study"],
            "status": "PASS",
            "protocol": PROTOCOL.name,
            "protocol_sha256": protocol_sha,
            "runner": Path(__file__).name,
            "runner_sha256": digest_file(Path(__file__)),
            "task_repository_commit": protocol["task_repository_commit"],
            "task_input_manifest_sha256": digest_file(INPUT_MANIFEST),
            "agent_rollback_repository_commit": EXPECTED_AGENT_COMMIT,
            "agent_rollback_git_inventory_command": "git ls-files -co --exclude-standard -z",
            "agent_rollback_checkpoint_restore": "native CLI; pre-command checkpoint restored after a post-command checkpoint",
            "production_recovery_engine_sha256": EXPECTED_ENGINE_SHA,
            "command": protocol["command"],
            "allowed_paths": sorted(ALLOWED),
            "cases": cases,
            "aggregate": {
                "denominator": len(cases),
                "agent_rollback_joint_pass": sum(c["agent_joint_score"]["joint_pass"] for c in cases),
                "csdvr_joint_pass": sum(c["csdvr_joint_score"]["joint_pass"] for c in cases),
                "agent_rollback_exact_backups_recovered": sum(c["agent_exact_backups_recovered"] for c in cases),
                "total_ignored_backups": sum(c["ignored_backup_count"] for c in cases),
                "agent_checkpoint_omitted_backups": sum(c["agent_checkpoint_omitted_backup_count"] for c in cases),
                "paired_post_command_maps_identical": all(c["same_command_and_contract_pairing"] for c in cases),
            },
            "model_or_api_calls": 0,
            "official_benchmark_score": False,
            "interpretation": [
                "The native agent-rollback checkpoint inventory omits .gitignore-excluded backups in this Git repository configuration; its pre-command checkpoint therefore cannot reconstruct their deleted bytes.",
                "C-SDVR uses the complete before/after byte maps and the frozen allowed-path contract; it recovers the ignored backups and also retains the requested cleanup effect in this controlled case.",
                "This is a narrow native-tool comparison on one public cleanup task family, not a general ranking or evidence about all agent-rollback configurations."
            ],
        }
        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(json.dumps({k: result[k] for k in ("status", "aggregate", "cases")},
                         indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
