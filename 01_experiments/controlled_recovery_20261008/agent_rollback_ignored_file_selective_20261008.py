#!/usr/bin/env python3
"""Best-effort native selective-revert plus contract replay comparison.

This addendum gives agent-rollback a contract-aware final step after its native
operation-level selective revert, while keeping the public command trajectory
and input bytes matched with C-SDVR.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPERS_PATH = HERE / "agent_rollback_ignored_file_same_trajectory_20261008.py"
PROTOCOL = HERE / "agent_rollback_ignored_file_selective_protocol_20261008.json"
OUTPUT = HERE / "agent_rollback_ignored_file_selective_20261008_results.json"
ALLOWED = {"build/main", "build/output.o"}


def load_helpers():
    spec = importlib.util.spec_from_file_location("agent_rollback_primary", HELPERS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper runner: {HELPERS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def field(obj: dict, name: str):
    for key, value in obj.items():
        if key.lower() == name.lower():
            return value
    return None


def main() -> None:
    h = load_helpers()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    protocol_sha = digest_file(PROTOCOL)
    source = h.verify_task_fixture("cleanup")
    if h.digest_file(h.ENGINE_PATH) != h.EXPECTED_ENGINE_SHA:
        raise RuntimeError("production recovery engine hash mismatch")
    engine = h.load_module("csdvr_engine_selective", h.ENGINE_PATH)
    scratch = Path(tempfile.mkdtemp(prefix="csdvr_agentrollback_selective_"))
    cases = []
    try:
        for count in (1, 10, 100):
            source_copy = scratch / f"baseline_source_{count}"
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
            for argv in (["git", "init", "-q"],
                         ["git", "config", "user.name", "C-SDVR replay"],
                         ["git", "config", "user.email", "csdvr-replay@example.invalid"],
                         ["git", "add", "-A"],
                         ["git", "commit", "-q", "-m", "frozen task baseline"]):
                h.run(list(argv), source_copy, f"git_baseline:{count}")
            ignored = [h.run(["git", "check-ignore", "-q", "--", p], source_copy,
                             f"verify_ignored:{p}", check=False)["return_code"] == 0
                       for p in backup_paths]
            if not all(ignored):
                raise RuntimeError(f"not all backup files ignored at scale {count}")

            baseline_root = scratch / f"reference_{count}"
            shutil.copytree(source_copy, baseline_root)
            baseline = h.snapshot(baseline_root)
            reference_log = h.run(["bash", "./clean.sh"], baseline_root,
                                  f"reference_cleanup:{count}")
            if reference_log["return_code"] != 0:
                raise RuntimeError(f"reference cleanup failed at scale {count}")
            observed = h.snapshot(baseline_root)

            agent_root = scratch / f"agent_selective_{count}"
            shutil.copytree(source_copy, agent_root)
            init_log, _ = h.cli_json(["init"], agent_root, f"agent_init:{count}")
            _, pre_manifest = h.cli_json(["checkpoint", "before-cleanup"], agent_root,
                                         f"agent_checkpoint_pre:{count}")
            pre_id = field(pre_manifest, "id")
            if not pre_id:
                raise RuntimeError("pre-command checkpoint ID missing")
            checkpoint_files = h.get_manifest_files(pre_manifest)
            task_log = h.run(["bash", "./clean.sh"], agent_root,
                             f"agent_cleanup:{count}")
            if task_log["return_code"] != 0:
                raise RuntimeError(f"agent command failed at scale {count}")
            agent_observed = h.snapshot(agent_root)
            if h.digest_map(agent_observed) != h.digest_map(observed):
                raise RuntimeError(f"paired post-command maps differ at scale {count}")
            _, post_manifest = h.cli_json(["checkpoint", "after-cleanup"], agent_root,
                                          f"agent_checkpoint_post:{count}")
            post_id = field(post_manifest, "id")
            operations_path = agent_root / ".agent-rollback" / "ops.jsonl"
            ops = [json.loads(line) for line in operations_path.read_text(encoding="utf-8").splitlines()]
            post_op = next((op for op in ops
                            if op.get("type") == "checkpoint.created"
                            and field(op.get("details", {}), "checkpointId") == post_id), None)
            if post_op is None:
                raise RuntimeError("could not map post-command checkpoint to native operation ID")
            op_log, op_payload = h.cli_json(["op", "revert", post_op["id"]], agent_root,
                                            f"agent_selective_revert:{count}")

            # Reapply only the contract-allowed post-command state, which in
            # this task means keeping both build artifacts deleted.
            for rel in sorted(ALLOWED):
                target = agent_root / rel
                if rel in observed:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(observed[rel])
                elif target.is_file() or target.is_symlink():
                    target.unlink()
            agent_final = h.snapshot(agent_root)

            projected = engine.project(baseline, observed, ALLOWED)
            csdvr_root = scratch / f"csdvr_{count}"
            shutil.copytree(baseline_root, csdvr_root)
            for rel in h.snapshot(csdvr_root).keys() - projected.keys():
                target = csdvr_root / rel
                if target.is_file() or target.is_symlink():
                    target.unlink()
            for rel, content in projected.items():
                target = csdvr_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            csdvr_final = h.snapshot(csdvr_root)
            recovered = [p for p in backup_paths if agent_final.get(p) == baseline.get(p)]
            cases.append({
                "ignored_backup_count": count,
                "paired_post_command_maps_identical": True,
                "agent_checkpoint_file_count": len(checkpoint_files),
                "agent_checkpoint_omitted_backup_count": sum(p not in checkpoint_files for p in backup_paths),
                "native_selective_revert_operation_id": post_op["id"],
                "native_selective_revert_paths": field(op_payload, "filesToTouch") or [],
                "native_selective_revert_applied": field(op_payload, "applied"),
                "contract_replay_allowed_paths": sorted(ALLOWED),
                "agent_exact_backups_recovered": len(recovered),
                "agent_selective_plus_replay_score": h.score(agent_final, baseline),
                "csdvr_score": h.score(csdvr_final, baseline),
                "agent_init_stdout": init_log["stdout"],
                "agent_pre_checkpoint_id": pre_id,
                "agent_post_checkpoint_id": post_id,
                "native_selective_revert_return_code": op_log["return_code"],
            })

        result = {
            "study": protocol["study"],
            "status": "PASS",
            "protocol": PROTOCOL.name,
            "protocol_sha256": protocol_sha,
            "runner": Path(__file__).name,
            "runner_sha256": digest_file(Path(__file__)),
            "tool_commit": protocol["tool_commit"],
            "task_repository_commit": protocol["task_repository_commit"],
            "task_input_manifest_sha256": h.digest_file(h.INPUT_MANIFEST),
            "method": "native agent-rollback op revert plus contract replay of allowed post-state paths",
            "model_or_api_calls": 0,
            "official_benchmark_score": False,
            "cases": cases,
            "aggregate": {
                "denominator": len(cases),
                "agent_selective_plus_replay_joint_pass": sum(c["agent_selective_plus_replay_score"]["joint_pass"] for c in cases),
                "csdvr_joint_pass": sum(c["csdvr_score"]["joint_pass"] for c in cases),
                "agent_exact_backups_recovered": sum(c["agent_exact_backups_recovered"] for c in cases),
                "total_ignored_backups": sum(c["ignored_backup_count"] for c in cases),
                "agent_checkpoint_omitted_backups": sum(c["agent_checkpoint_omitted_backup_count"] for c in cases),
                "paired_post_command_maps_identical": all(c["paired_post_command_maps_identical"] for c in cases),
            },
            "interpretation": [
                "The best-effort selective arm explicitly reapplies the allowed cleanup output after native selective revert; it still cannot restore ignored backup bytes absent from the checkpoint inventory.",
                "This identifies an advantage over this pinned tool's default Git-aware inventory in the controlled ignored-file case; it is not a general comparison against other configurations or recovery tools."
            ]
        }
        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(json.dumps({"status": result["status"], "aggregate": result["aggregate"],
                          "cases": [{"count": c["ignored_backup_count"],
                                     "selective_paths": c["native_selective_revert_paths"],
                                     "agent_score": c["agent_selective_plus_replay_score"]["joint_pass"],
                                     "csdvr_score": c["csdvr_score"]["joint_pass"],
                                     "omitted": c["agent_checkpoint_omitted_backup_count"]}
                                    for c in cases]}, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
