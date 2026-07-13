#!/usr/bin/env python3
"""Measure repository snapshot, diff, verification, and rollback overhead.

The benchmark creates synthetic local Git repositories of increasing size,
mutates a bounded set of tracked files, verifies the exact intended diff, and
restores the changed bytes. It performs no network or external repository I/O.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "02_results"
RAW = OUT / "ase_repository_scalability_raw_v6.csv"
SUMMARY = OUT / "ase_repository_scalability_summary_v6.csv"
REPORT = OUT / "ase_repository_scalability_report_v6.md"
FIG_PNG = OUT / "figures" / "ase_repository_scalability_v6.png"
FIG_PDF = OUT / "figures" / "ase_repository_scalability_v6.pdf"


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def create_repository(root: Path, file_count: int, file_size: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    alphabet = "0123456789abcdef"
    for index in range(file_count):
        group = index // 100
        path = root / "src" / f"module_{group:03d}" / f"file_{index:06d}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        header = f"record={index:06d}\n"
        body_length = max(0, file_size - len(header.encode("utf-8")) - 1)
        pattern = (alphabet * ((body_length // len(alphabet)) + 1))[:body_length]
        path.write_text(header + pattern + "\n", encoding="utf-8")
    (root / "README.md").write_text(
        f"Synthetic repository with {file_count} generated source objects.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "artifact@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Artifact Runner"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)


def tracked_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts and path.name != "README.md"
    )


def snapshot(root: Path) -> tuple[dict[str, bytes], dict[str, str]]:
    content: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.relative_to(root).parts:
            continue
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        content[relative] = payload
        hashes[relative] = hashlib.sha256(payload).hexdigest()
    return content, hashes


def hash_state(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.relative_to(root).parts:
            continue
        relative = path.relative_to(root).as_posix()
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def state_diff(before_hashes: dict[str, str], after_hashes: dict[str, str]) -> list[str]:
    return sorted(
        path
        for path in set(before_hashes) | set(after_hashes)
        if before_hashes.get(path) != after_hashes.get(path)
    )


def mutate(paths: list[Path], repeat: int) -> int:
    changed_bytes = 0
    for index, path in enumerate(paths):
        payload = path.read_bytes()
        marker = f"mutation={repeat:03d}:{index:03d}\n".encode("utf-8")
        if len(payload) >= len(marker):
            updated = marker + payload[len(marker) :]
        else:
            updated = marker
        path.write_bytes(updated)
        changed_bytes += len(updated)
    return changed_bytes


def restore(root: Path, before: dict[str, bytes], changed: list[str]) -> int:
    restored = 0
    for relative in changed:
        path = root / relative
        if relative in before:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = before[relative]
            path.write_bytes(payload)
            restored += len(payload)
        else:
            path.unlink(missing_ok=True)
    return restored


def git_clean(root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout.strip()


def run_case(root: Path, candidates: list[Path], file_count: int, file_size: int, width: int, repeat: int) -> dict[str, Any]:
    rng = random.Random(910_000 + file_count * 31 + file_size * 7 + width * 3 + repeat)
    selected = rng.sample(candidates, min(width, len(candidates)))
    selected_rel = {path.relative_to(root).as_posix() for path in selected}

    started = time.perf_counter_ns()
    before_content, before_hashes = snapshot(root)
    snapshot_done = time.perf_counter_ns()
    changed_bytes = mutate(selected, repeat)
    mutation_done = time.perf_counter_ns()
    after_hashes = hash_state(root)
    hash_done = time.perf_counter_ns()
    diff = state_diff(before_hashes, after_hashes)
    diff_done = time.perf_counter_ns()
    verified = set(diff) == selected_rel and all(after_hashes[path] != before_hashes[path] for path in diff)
    verify_done = time.perf_counter_ns()
    restored_bytes = restore(root, before_content, diff)
    rollback_done = time.perf_counter_ns()
    final_hashes = hash_state(root)
    final_done = time.perf_counter_ns()
    rollback_success = final_hashes == before_hashes and git_clean(root)

    ns_to_ms = 1 / 1_000_000
    return {
        "repository_files": file_count,
        "file_size_bytes": file_size,
        "mutation_width": len(selected),
        "repeat": repeat,
        "snapshot_ms": (snapshot_done - started) * ns_to_ms,
        "mutation_ms": (mutation_done - snapshot_done) * ns_to_ms,
        "post_hash_ms": (hash_done - mutation_done) * ns_to_ms,
        "diff_ms": (diff_done - hash_done) * ns_to_ms,
        "verification_ms": (verify_done - diff_done) * ns_to_ms,
        "rollback_ms": (rollback_done - verify_done) * ns_to_ms,
        "final_hash_ms": (final_done - rollback_done) * ns_to_ms,
        "total_control_ms": (final_done - started) * ns_to_ms,
        "snapshot_bytes": sum(len(payload) for payload in before_content.values()),
        "changed_bytes": changed_bytes,
        "rollback_bytes": restored_bytes,
        "diff_entries": len(diff),
        "verification_correct": verified,
        "rollback_success": rollback_success,
        "state_hash": hashlib.sha256(json.dumps(final_hashes, sort_keys=True).encode("utf-8")).hexdigest()[:12],
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["repository_files"]), int(row["file_size_bytes"]), int(row["mutation_width"]))].append(row)
    result: list[dict[str, Any]] = []
    metrics = ["snapshot_ms", "post_hash_ms", "diff_ms", "verification_ms", "rollback_ms", "total_control_ms"]
    for (files, file_size, width), values in sorted(grouped.items()):
        output: dict[str, Any] = {
            "repository_files": files,
            "file_size_bytes": file_size,
            "mutation_width": width,
            "runs": len(values),
            "snapshot_bytes": int(statistics.mean(float(row["snapshot_bytes"]) for row in values)),
            "rollback_bytes": int(statistics.mean(float(row["rollback_bytes"]) for row in values)),
            "verification_accuracy": statistics.mean(float(row["verification_correct"]) for row in values),
            "rollback_success": statistics.mean(float(row["rollback_success"]) for row in values),
        }
        for metric in metrics:
            samples = [float(row[metric]) for row in values]
            output[f"mean_{metric}"] = statistics.mean(samples)
            output[f"p95_{metric}"] = percentile(samples, 0.95)
        result.append(output)
    return result


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_figure(summary_rows: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    FIG_PNG.parent.mkdir(parents=True, exist_ok=True)
    selected = [
        row for row in summary_rows
        if int(row["file_size_bytes"]) == 1024 and int(row["mutation_width"]) == 10
    ]
    x = [int(row["repository_files"]) for row in selected]
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    ax.plot(x, [float(row["mean_snapshot_ms"]) for row in selected], marker="o", label="Snapshot")
    ax.plot(x, [float(row["mean_post_hash_ms"]) + float(row["mean_diff_ms"]) for row in selected], marker="s", label="Post-state hash + diff")
    ax.plot(x, [float(row["mean_rollback_ms"]) for row in selected], marker="^", label="Rollback (10 files)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Tracked repository files")
    ax.set_ylabel("Mean wall-clock time (ms, log scale)")
    ax.grid(True, which="both", linewidth=0.5, alpha=0.35)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_PNG, dpi=300)
    fig.savefig(FIG_PDF)
    plt.close(fig)


def write_report(rows: list[dict[str, Any]], summary_rows: list[dict[str, Any]], smoke: bool) -> None:
    lines = [
        "# ASE Repository Scalability Validation v6",
        "",
        f"Smoke mode: {smoke}",
        f"Raw runs: {len(rows)}",
        f"Verification failures: {sum(not bool(row['verification_correct']) for row in rows)}",
        f"Rollback failures: {sum(not bool(row['rollback_success']) for row in rows)}",
        "Measurements use synthetic local Git repositories and include complete content snapshots. They are machine-specific engineering measurements, not asymptotic guarantees.",
        "",
        "| Files | Bytes/file | Changed | Snapshot ms | Hash+diff ms | Verify ms | Rollback ms | Snapshot MiB |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['repository_files']} | {row['file_size_bytes']} | {row['mutation_width']} | "
            f"{row['mean_snapshot_ms']:.3f} | {row['mean_post_hash_ms'] + row['mean_diff_ms']:.3f} | "
            f"{row['mean_verification_ms']:.4f} | {row['mean_rollback_ms']:.3f} | "
            f"{row['snapshot_bytes'] / (1024 * 1024):.3f} |"
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    file_counts = [50, 250, 1000, 2500]
    file_sizes = [1024, 8192]
    widths = [1, 10, 50]
    repeats = max(1, int(os.getenv("CSDVR_SCALE_REPEATS", "8")))
    if args.smoke:
        file_counts = [50]
        file_sizes = [1024]
        widths = [1, 10]
        repeats = 1

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="csdvr_scale_") as tmp:
        root_base = Path(tmp)
        total_groups = len(file_counts) * len(file_sizes)
        group_index = 0
        for file_count in file_counts:
            for file_size in file_sizes:
                group_index += 1
                repo = root_base / f"repo_{file_count}_{file_size}"
                create_repository(repo, file_count, file_size)
                candidates = tracked_files(repo)
                for width in widths:
                    for repeat in range(repeats):
                        row = run_case(repo, candidates, file_count, file_size, width, repeat)
                        rows.append(row)
                print(f"ase_scalability_progress={group_index}/{total_groups}", flush=True)

    expected = len(file_counts) * len(file_sizes) * len(widths) * repeats
    if len(rows) != expected:
        raise RuntimeError(f"row-count mismatch: expected {expected}, got {len(rows)}")
    if any(not row["verification_correct"] or not row["rollback_success"] for row in rows):
        raise RuntimeError("verification or rollback integrity check failed")
    summary_rows = summarize(rows)
    write_csv(RAW if not args.smoke else OUT / "ase_repository_scalability_smoke_raw_v6.csv", rows)
    write_csv(SUMMARY if not args.smoke else OUT / "ase_repository_scalability_smoke_summary_v6.csv", summary_rows)
    if not args.smoke:
        make_figure(summary_rows)
    write_report(rows, summary_rows, args.smoke)
    print(REPORT)
    print(f"ase_scalability_runs={len(rows)}")


if __name__ == "__main__":
    main()
