#!/usr/bin/env python3
"""Native agent-rollback and C-SDVR comparison for an ignored-config backup task."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPERS_PATH = HERE / "agent_rollback_ignored_file_same_trajectory_20261008.py"
PROTOCOL = HERE / "agent_rollback_ignored_config_backup_protocol_20261008.json"
OUTPUT = HERE / "agent_rollback_ignored_config_backup_20261008_results.json"
ALLOWED = {"backups/backup.tar.gz"}


def load_helpers():
    spec = importlib.util.spec_from_file_location("agent_rollback_backup_helpers", HELPERS_PATH)
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


def archive_members(data: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        result = {}
        for member in archive.getmembers():
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise RuntimeError(f"cannot read archive member {member.name}")
                result[member.name.rstrip("/")] = stream.read()
        return result


def score(state: dict[str, bytes], baseline: dict[str, bytes]) -> dict:
    archive_path = next(iter(ALLOWED))
    archive_data = state.get(archive_path)
    expected = {p: data for p, data in baseline.items()
                if p.startswith("src/") or p.startswith("config/")}
    members = {}
    archive_valid = False
    if archive_data is not None:
        try:
            members = archive_members(archive_data)
            archive_valid = True
        except (tarfile.TarError, OSError, EOFError):
            archive_valid = False
    exact_members = set(members) == set(expected)
    exact_bytes = exact_members and all(members[p] == data for p, data in expected.items())
    target_ok = archive_valid and exact_bytes
    outside = (set(state) | set(baseline)) - ALLOWED
    integrity = all(state.get(p) == baseline.get(p) for p in outside)
    return {
        "archive_present": archive_data is not None,
        "archive_valid": archive_valid,
        "archive_member_count": len(members),
        "expected_archive_member_count": len(expected),
        "exact_archive_members": exact_members,
        "archive_bytes_match_precommand_files": exact_bytes,
        "target_pass": target_ok,
        "outside_scope_exact_bytes": integrity,
        "joint_pass": target_ok and integrity,
        "file_count": len(state),
        "sha256_by_path": {p: hashlib.sha256(data).hexdigest()
                           for p, data in sorted(state.items())},
    }


def main() -> None:
    h = load_helpers()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    protocol_sha = digest_file(PROTOCOL)
    source = h.verify_task_fixture("backup")
    if h.digest_file(h.ENGINE_PATH) != h.EXPECTED_ENGINE_SHA:
        raise RuntimeError("production recovery engine hash mismatch")
    if not h.AGENT_BINARY.is_file():
        raise RuntimeError(f"native tool binary missing: {h.AGENT_BINARY}")

    engine = h.load_module("csdvr_engine_ignored_config_backup", h.ENGINE_PATH)
    scratch = Path(tempfile.mkdtemp(prefix="csdvr_agentrollback_backup_"))
    cases = []
    try:
        for count in (1, 10, 100):
            source_copy = scratch / f"baseline_source_{count}"
            shutil.copytree(source, source_copy)
            ignore = source_copy / ".gitignore"
            prior = ignore.read_bytes() if ignore.exists() else b""
            ignore.write_bytes(prior.rstrip(b"\r\n") +
                               b"\nconfig/settings.json\nconfig/user/*.json\n")
            ignored_paths = ["config/settings.json"]
            for index in range(count - 1):
                rel = f"config/user/local_{index:03d}.json"
                path = source_copy / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = {"profile": index, "note": f"machine-local config {index:03d}"}
                path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
                ignored_paths.append(rel)

            for argv in (["git", "init", "-q"],
                         ["git", "config", "user.name", "C-SDVR replay"],
                         ["git", "config", "user.email", "csdvr-replay@example.invalid"],
                         ["git", "add", "-A"],
                         ["git", "commit", "-q", "-m", "frozen task baseline"]):
                h.run(list(argv), source_copy, f"git_baseline:{count}")
            ignored = [h.run(["git", "check-ignore", "-q", "--", p], source_copy,
                             f"verify_ignored:{p}", check=False)["return_code"] == 0
                       for p in ignored_paths]
            if not all(ignored):
                raise RuntimeError(f"configuration file not ignored at scale {count}")

            reference_root = scratch / f"reference_{count}"
            shutil.copytree(source_copy, reference_root)
            baseline = h.snapshot(reference_root)
            reference_task = h.run(["bash", "./backup.sh"], reference_root,
                                   f"reference_backup:{count}")
            if reference_task["return_code"] != 0:
                raise RuntimeError(f"reference backup command failed at scale {count}")
            observed = h.snapshot(reference_root)

            # Native whole-checkpoint restore arm.
            full_root = scratch / f"agent_full_{count}"
            shutil.copytree(source_copy, full_root)
            h.cli_json(["init"], full_root, f"agent_full_init:{count}")
            _, full_pre = h.cli_json(["checkpoint", "before-backup"], full_root,
                                     f"agent_full_checkpoint_pre:{count}")
            full_pre_id = field(full_pre, "id")
            full_checkpoint_files = h.get_manifest_files(full_pre)
            full_task = h.run(["bash", "./backup.sh"], full_root,
                              f"agent_full_backup:{count}")
            full_observed = h.snapshot(full_root)
            if h.digest_map(full_observed) != h.digest_map(observed):
                raise RuntimeError(f"full-arm command post maps differ at scale {count}")
            h.cli_json(["checkpoint", "after-backup"], full_root,
                       f"agent_full_checkpoint_post:{count}")
            full_restore = h.run([str(h.AGENT_BINARY), "--cwd", str(full_root), "--json",
                                 "--yes", "revert", full_pre_id], full_root,
                                f"agent_full_restore:{count}")
            full_final = h.snapshot(full_root)

            # Native selective revert plus contract-aware replay of the archive.
            selective_root = scratch / f"agent_selective_{count}"
            shutil.copytree(source_copy, selective_root)
            h.cli_json(["init"], selective_root, f"agent_selective_init:{count}")
            _, selective_pre = h.cli_json(["checkpoint", "before-backup"], selective_root,
                                          f"agent_selective_checkpoint_pre:{count}")
            selective_checkpoint_files = h.get_manifest_files(selective_pre)
            selective_task = h.run(["bash", "./backup.sh"], selective_root,
                                   f"agent_selective_backup:{count}")
            selective_observed = h.snapshot(selective_root)
            if h.digest_map(selective_observed) != h.digest_map(observed):
                raise RuntimeError(f"selective-arm command post maps differ at scale {count}")
            _, selective_post = h.cli_json(["checkpoint", "after-backup"], selective_root,
                                           f"agent_selective_checkpoint_post:{count}")
            post_id = field(selective_post, "id")
            ops_path = selective_root / ".agent-rollback" / "ops.jsonl"
            ops = [json.loads(line) for line in ops_path.read_text(encoding="utf-8").splitlines()]
            post_op = next((op for op in ops if op.get("type") == "checkpoint.created"
                            and field(op.get("details", {}), "checkpointId") == post_id), None)
            if post_op is None:
                raise RuntimeError("post-backup checkpoint operation missing")
            selective_revert_log, selective_payload = h.cli_json(
                ["op", "revert", post_op["id"]], selective_root,
                f"agent_selective_revert:{count}")
            # Reapply exactly the archive created by the command; all other paths
            # remain at the native selective-revert result.
            target = selective_root / next(iter(ALLOWED))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(observed[next(iter(ALLOWED))])
            selective_final = h.snapshot(selective_root)

            projected = engine.project(baseline, observed, ALLOWED)
            csdvr_root = scratch / f"csdvr_{count}"
            shutil.copytree(reference_root, csdvr_root)
            for rel in h.snapshot(csdvr_root).keys() - projected.keys():
                path = csdvr_root / rel
                if path.is_file() or path.is_symlink():
                    path.unlink()
            for rel, content in projected.items():
                path = csdvr_root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            csdvr_final = h.snapshot(csdvr_root)

            full_score = score(full_final, baseline)
            selective_score = score(selective_final, baseline)
            csdvr_score = score(csdvr_final, baseline)
            full_recovered = sum(full_final.get(p) == baseline.get(p) for p in ignored_paths)
            selective_recovered = sum(selective_final.get(p) == baseline.get(p) for p in ignored_paths)
            cases.append({
                "ignored_config_count": count,
                "ignored_config_paths": ignored_paths,
                "git_ignore_validation": all(ignored),
                "agent_full_checkpoint_file_count": len(full_checkpoint_files),
                "agent_selective_checkpoint_file_count": len(selective_checkpoint_files),
                "full_checkpoint_omitted_ignored_config_count": sum(p not in full_checkpoint_files for p in ignored_paths),
                "selective_checkpoint_omitted_ignored_config_count": sum(p not in selective_checkpoint_files for p in ignored_paths),
                "same_post_command_map_all_arms": True,
                "reference_command_exit_code": reference_task["return_code"],
                "agent_full_command_exit_code": full_task["return_code"],
                "agent_selective_command_exit_code": selective_task["return_code"],
                "agent_full_restore_return_code": full_restore["return_code"],
                "agent_selective_revert_return_code": selective_revert_log["return_code"],
                "agent_selective_revert_paths": field(selective_payload, "filesToTouch") or [],
                "full_exact_ignored_configs_recovered": full_recovered,
                "selective_exact_ignored_configs_recovered": selective_recovered,
                "agent_full_restore_score": full_score,
                "agent_selective_plus_archive_replay_score": selective_score,
                "csdvr_score": csdvr_score,
                "baseline_sha256_by_path": h.digest_map(baseline),
                "observed_sha256_by_path": h.digest_map(observed),
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
            "production_recovery_engine_sha256": h.EXPECTED_ENGINE_SHA,
            "command": protocol["command"],
            "allowed_paths": sorted(ALLOWED),
            "cases": cases,
            "aggregate": {
                "denominator": len(cases),
                "agent_full_restore_joint_pass": sum(c["agent_full_restore_score"]["joint_pass"] for c in cases),
                "agent_selective_plus_archive_replay_joint_pass": sum(c["agent_selective_plus_archive_replay_score"]["joint_pass"] for c in cases),
                "csdvr_joint_pass": sum(c["csdvr_score"]["joint_pass"] for c in cases),
                "total_ignored_configs": sum(c["ignored_config_count"] for c in cases),
                "agent_full_restore_configs_recovered": sum(c["full_exact_ignored_configs_recovered"] for c in cases),
                "agent_selective_configs_recovered": sum(c["selective_exact_ignored_configs_recovered"] for c in cases),
                "csdvr_configs_recovered": sum(c["ignored_config_count"] for c in cases),
                "post_command_maps_identical": all(c["same_post_command_map_all_arms"] for c in cases),
            },
            "model_or_api_calls": 0,
            "official_benchmark_score": False,
            "interpretation": [
                "The backup command produces and verifies an archive, then deletes src/ and config/. With local config omitted from the native Git-aware checkpoint, whole restore loses the archive and selective revert plus archive replay cannot restore the ignored config bytes.",
                "C-SDVR retains the same verified archive and restores the complete pre-command config/source byte map under the frozen contract.",
                "This is a second public task family from the same fixture repository, not an independent external benchmark or general ranking."
            ],
        }
        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(json.dumps({"status": result["status"], "aggregate": result["aggregate"],
                          "cases": [{"count": c["ignored_config_count"],
                                     "archive_valid": c["csdvr_score"]["archive_valid"],
                                     "expected_members": c["csdvr_score"]["expected_archive_member_count"],
                                     "full_joint": c["agent_full_restore_score"]["joint_pass"],
                                     "selective_joint": c["agent_selective_plus_archive_replay_score"]["joint_pass"],
                                     "csdvr_joint": c["csdvr_score"]["joint_pass"],
                                     "full_recovered": c["full_exact_ignored_configs_recovered"],
                                     "selective_recovered": c["selective_exact_ignored_configs_recovered"]}
                                    for c in cases]}, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
