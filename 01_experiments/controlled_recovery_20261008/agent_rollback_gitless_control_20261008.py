#!/usr/bin/env python3
"""Gitless fallback-scan control for the ignored-backup recovery experiment."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPERS_PATH = HERE / "agent_rollback_ignored_file_same_trajectory_20261008.py"
PROTOCOL = HERE / "agent_rollback_gitless_control_protocol_20261008.json"
OUTPUT = HERE / "agent_rollback_gitless_control_20261008_results.json"
ALLOWED = {"build/main", "build/output.o"}


def load_helpers():
    spec = importlib.util.spec_from_file_location("agent_rollback_gitless_helpers", HELPERS_PATH)
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
    return next((value for key, value in obj.items() if key.lower() == name.lower()), None)


def main() -> None:
    h = load_helpers()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    source = h.verify_task_fixture("cleanup")
    if h.digest_file(h.ENGINE_PATH) != h.EXPECTED_ENGINE_SHA:
        raise RuntimeError("production recovery engine hash mismatch")
    if not h.AGENT_BINARY.is_file():
        raise RuntimeError(f"native agent-rollback binary missing: {h.AGENT_BINARY}")

    engine = h.load_module("csdvr_gitless_control_engine", h.ENGINE_PATH)
        cases = []

        for count in (1, 10, 100):
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

            git_probe = h.run(["git", "rev-parse", "--is-inside-work-tree"], source_copy,
                              f"verify_no_git_repo:{count}", check=False)
            if git_probe["return_code"] == 0:
                raise RuntimeError("control fixture unexpectedly resides in a Git repository")

            reference_root = scratch / f"reference_{count}"
            shutil.copytree(source_copy, reference_root)
            baseline = h.snapshot(reference_root)
            reference_task = h.run(["bash", "./clean.sh"], reference_root, f"reference_cleanup:{count}")
            if reference_task["return_code"] != 0:
                raise RuntimeError(f"reference cleanup failed at scale {count}")
            observed = h.snapshot(reference_root)

            agent_root = scratch / f"agent_{count}"
            shutil.copytree(source_copy, agent_root)
            init_log, _ = h.cli_json(["init"], agent_root, f"agent_init:{count}")
            _, pre_manifest = h.cli_json(["checkpoint", "before-cleanup"], agent_root,
                                         f"agent_checkpoint_pre:{count}")
            pre_id = field(pre_manifest, "id")
            if not pre_id:
                raise RuntimeError("pre-command checkpoint ID missing")
            checkpoint_files = h.get_manifest_files(pre_manifest)
            recorded_backups = sorted(path for path in backup_paths if path in checkpoint_files)

            task_log = h.run(["bash", "./clean.sh"], agent_root, f"agent_cleanup:{count}")
            if task_log["return_code"] != 0:
                raise RuntimeError(f"agent cleanup failed at scale {count}")
            agent_observed = h.snapshot(agent_root)
            paired = h.digest_map(agent_observed) == h.digest_map(observed)
            if not paired:
                raise RuntimeError(f"paired command-post maps differ at scale {count}")

            _, post_manifest = h.cli_json(["checkpoint", "after-cleanup"], agent_root,
                                          f"agent_checkpoint_post:{count}")
            post_id = field(post_manifest, "id")
            ops_path = agent_root / ".agent-rollback" / "ops.jsonl"
            ops = [json.loads(line) for line in ops_path.read_text(encoding="utf-8").splitlines()]
            post_op = next((op for op in ops if op.get("type") == "checkpoint.created"
                            and field(op.get("details", {}), "checkpointId") == post_id), None)
            if post_op is None:
                raise RuntimeError("could not map post-command checkpoint to operation ID")
            revert_log, revert_payload = h.cli_json(["op", "revert", post_op["id"]], agent_root,
                                                    f"agent_selective_revert:{count}")
            for rel in sorted(ALLOWED):
                target = agent_root / rel
                if rel in observed:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(observed[rel])
                elif target.is_file() or target.is_symlink():
                    target.unlink()
            agent_final = h.snapshot(agent_root)

            candidate = engine.project(baseline, observed, ALLOWED)
            csdvr_root = scratch / f"csdvr_{count}"
            shutil.copytree(reference_root, csdvr_root)
            for rel in h.snapshot(csdvr_root).keys() - candidate.keys():
                target = csdvr_root / rel
                if target.is_file() or target.is_symlink():
                    target.unlink()
            for rel, content in candidate.items():
                target = csdvr_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            csdvr_final = h.snapshot(csdvr_root)

            cases.append({
                "backup_count": count,
                "git_repository_absent": True,
                "same_post_command_map": paired,
                "checkpoint_file_count": len(checkpoint_files),
                "checkpoint_recorded_backups": len(recorded_backups),
                "checkpoint_omitted_backups": count - len(recorded_backups),
                "native_revert_paths": field(revert_payload, "filesToTouch") or [],
                "native_revert_return_code": revert_log["return_code"],
                "agent_exact_backups_recovered": sum(agent_final.get(p) == baseline.get(p) for p in backup_paths),
                "agent_score": h.score(agent_final, baseline),
                "csdvr_score": h.score(csdvr_final, baseline),
                "init_stdout": init_log["stdout"],
            })

        result = {
            "study": protocol["study"],
            "status": "PASS",
            "protocol": PROTOCOL.name,
            "protocol_sha256": digest_file(PROTOCOL),
            "runner": Path(__file__).name,
            "runner_sha256": digest_file(Path(__file__)),
            "tool_commit": protocol["tool_commit"],
            "task_repository_commit": protocol["task_repository_commit"],
            "task_input_manifest_sha256": h.digest_file(h.INPUT_MANIFEST),
            "production_engine_sha256": h.digest_file(h.ENGINE_PATH),
            "model_or_api_calls": 0,
            "official_benchmark_score": False,
            "cases": cases,
            "aggregate": {
                "denominator": len(cases),
                "agent_joint_pass": sum(c["agent_score"]["joint_pass"] for c in cases),
                "csdvr_joint_pass": sum(c["csdvr_score"]["joint_pass"] for c in cases),
                "total_backups": sum(c["backup_count"] for c in cases),
                "agent_checkpoint_recorded_backups": sum(c["checkpoint_recorded_backups"] for c in cases),
                "agent_exact_backups_recovered": sum(c["agent_exact_backups_recovered"] for c in cases),
                "paired_post_command_maps_identical": all(c["same_post_command_map"] for c in cases),
            },
            "interpretation": [
                "This is a boundary control for the documented non-Git filesystem-walk fallback.",
                "A pass here limits the selective advantage to Git repositories where the default scanner excludes .gitignore paths; it does not support universal superiority."
            ]
        }
        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"], "aggregate": result["aggregate"],
                          "cases": [{"backup_count": c["backup_count"],
                                     "recorded": c["checkpoint_recorded_backups"],
                                     "agent_pass": c["agent_score"]["joint_pass"],
                                     "csdvr_pass": c["csdvr_score"]["joint_pass"]}
                                    for c in cases]}, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
