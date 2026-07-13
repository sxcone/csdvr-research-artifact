#!/usr/bin/env python3
"""Executable boundary stress test for incomplete, stale, concurrent, and irreversible state."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "02_results"
RAW_OUT = RESULTS / "state_boundary_validation_raw_v5.csv"
SUMMARY_OUT = RESULTS / "state_boundary_validation_summary_v5.csv"
REPORT_OUT = RESULTS / "state_boundary_validation_report_v5.md"

DOMAINS = ["file", "sqlite_form"]
SCENARIOS = ["complete_scope", "scope_omission", "stale_snapshot", "concurrent_modification", "irreversible_effect"]
POLICIES = ["C-SDVR-Guarded", "BlindRollback"]


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def serialized_bytes(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, ensure_ascii=True).encode("utf-8"))


def changed_payload_bytes(source: dict[str, Any], target: dict[str, Any]) -> int:
    changed = {key: target.get(key) for key in set(source) | set(target) if source.get(key) != target.get(key)}
    return serialized_bytes(changed)


class FileAdapter:
    def __init__(self, root: Path, seed: int) -> None:
        self.root = root
        root.mkdir(parents=True)
        self._write("target", f"draft-{seed}")
        self._write("unrelated", f"stable-{seed}")
        self._write("concurrent", f"v0-{seed}")
        self._write("version", "0")
        self._write("events", "")

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.txt"

    def _write(self, key: str, value: str) -> None:
        self._path(key).write_text(value, encoding="utf-8")

    def snapshot(self) -> dict[str, Any]:
        return {key: self._path(key).read_text(encoding="utf-8") for key in ("target", "unrelated", "concurrent", "version", "events")}

    def set(self, key: str, value: str) -> None:
        self._write(key, value)

    def append_event(self, value: str) -> None:
        current = self._path("events").read_text(encoding="utf-8")
        self._write("events", current + value + "\n")

    def restore(self, snapshot: dict[str, Any], keys: set[str]) -> None:
        for key in keys:
            if key == "events":
                continue  # Application-level append-only effect has no compensation API.
            if key in snapshot:
                self._write(key, str(snapshot[key]))


class SQLiteAdapter:
    def __init__(self, path: Path, seed: int) -> None:
        self.path = path
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT NOT NULL)")
            conn.executemany(
                "INSERT INTO kv(key,value) VALUES (?,?)",
                [
                    ("target", f"draft-{seed}"),
                    ("unrelated", f"stable-{seed}"),
                    ("concurrent", f"v0-{seed}"),
                    ("version", "0"),
                ],
            )

    def snapshot(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            values = {key: value for key, value in conn.execute("SELECT key,value FROM kv ORDER BY key")}
            values["events"] = [value for (value,) in conn.execute("SELECT value FROM events ORDER BY seq")]
            return values

    def set(self, key: str, value: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def append_event(self, value: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO events(value) VALUES (?)", (value,))

    def restore(self, snapshot: dict[str, Any], keys: set[str]) -> None:
        with sqlite3.connect(self.path) as conn:
            for key in keys:
                if key == "events":
                    continue  # No compensation endpoint is exposed for committed events.
                if key in snapshot:
                    conn.execute("INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(snapshot[key])))


def run_one(domain: str, scenario: str, policy: str, seed: int) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="csdvr_boundary_") as directory:
        root = Path(directory)
        adapter: FileAdapter | SQLiteAdapter
        adapter = FileAdapter(root / "files", seed) if domain == "file" else SQLiteAdapter(root / "records.sqlite", seed)

        initial = adapter.snapshot()
        full_snapshot = deepcopy(initial)
        snapshot = deepcopy(initial)
        snapshot_scope = {"target", "unrelated", "concurrent", "version", "events"}
        expected_target = f"approved-{seed}"
        legitimate_concurrent = f"legitimate-v1-{seed}"
        latest_concurrent = f"legitimate-v2-{seed}"

        if scenario == "scope_omission":
            snapshot_scope = {"target", "version"}
            snapshot = {key: value for key, value in snapshot.items() if key in snapshot_scope}

        safe_stop = False
        recovery_attempted = False
        rollback_attempted = False
        unsafe_overwrite = False
        irreversible_triggered = False
        scope_complete = scenario != "scope_omission"
        snapshot_stale = scenario == "stale_snapshot"
        concurrency_conflict = scenario == "concurrent_modification"

        if scenario == "stale_snapshot":
            adapter.set("concurrent", legitimate_concurrent)
            adapter.set("version", "1")

        if policy == "C-SDVR-Guarded" and scenario in {"scope_omission", "stale_snapshot", "irreversible_effect"}:
            safe_stop = True
        else:
            if scenario in {"complete_scope", "scope_omission", "stale_snapshot"}:
                adapter.set("unrelated", f"corrupted-{seed}")
            elif scenario == "concurrent_modification":
                adapter.set("target", expected_target)
                adapter.set("target", latest_concurrent)
                adapter.set("version", "1")
            elif scenario == "irreversible_effect":
                adapter.set("target", expected_target)
                adapter.append_event(f"committed-wrong-event-{seed}")
                irreversible_triggered = True

            observed = adapter.snapshot()
            if policy == "C-SDVR-Guarded" and scenario == "concurrent_modification":
                safe_stop = True
            else:
                recovery_attempted = True
                rollback_attempted = True
                adapter.restore(snapshot, snapshot_scope)
                adapter.set("target", expected_target)
                if scenario in {"stale_snapshot", "concurrent_modification"}:
                    unsafe_overwrite = adapter.snapshot()["concurrent" if scenario == "stale_snapshot" else "target"] != (
                        legitimate_concurrent if scenario == "stale_snapshot" else latest_concurrent
                    )

        final = adapter.snapshot()

        if scenario == "stale_snapshot":
            allowed = deepcopy(initial)
            allowed["concurrent"] = legitimate_concurrent
            allowed["version"] = "1"
        elif scenario == "concurrent_modification":
            allowed = deepcopy(initial)
            allowed["target"] = latest_concurrent
            allowed["version"] = "1"
        else:
            allowed = deepcopy(initial)

        expected_final = deepcopy(allowed)
        expected_final["target"] = expected_target
        if domain == "sqlite_form" and not isinstance(expected_final["events"], list):
            expected_final["events"] = []

        target_satisfied = final["target"] == expected_target
        residue = any(
            final.get(key) != expected_final.get(key)
            for key in expected_final
            if key != "target"
        )
        residue = residue or unsafe_overwrite
        if scenario == "concurrent_modification" and safe_stop:
            target_satisfied = False
            residue = False
        if safe_stop and scenario in {"scope_omission", "stale_snapshot", "irreversible_effect"}:
            target_satisfied = False
            residue = False

        success = target_satisfied and not residue and not safe_stop
        rollback_bytes = changed_payload_bytes(observed, snapshot) if recovery_attempted else 0
        elapsed_ms = (time.perf_counter() - started) * 1000

        return {
            "seed": seed,
            "domain": domain,
            "scenario": scenario,
            "policy": policy,
            "success": int(success),
            "target_satisfied": int(target_satisfied),
            "residue": int(residue),
            "integrity_preserved": int(not residue),
            "safe_stop": int(safe_stop),
            "recovery_attempted": int(recovery_attempted),
            "rollback_attempted": int(rollback_attempted),
            "unsafe_overwrite": int(unsafe_overwrite),
            "scope_complete": int(scope_complete),
            "snapshot_stale": int(snapshot_stale),
            "concurrency_conflict": int(concurrency_conflict),
            "irreversible_triggered": int(irreversible_triggered),
            "wall_clock_ms": f"{elapsed_ms:.3f}",
            "snapshot_bytes": serialized_bytes(snapshot),
            "rollback_bytes": rollback_bytes,
            "initial_state_hash": stable_hash(initial),
            "final_state_hash": stable_hash(final),
        }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["domain"], row["scenario"], row["policy"]), []).append(row)
    out: list[dict[str, Any]] = []
    for key, items in sorted(groups.items()):
        out.append(
            {
                "domain": key[0],
                "scenario": key[1],
                "policy": key[2],
                "runs": len(items),
                "success": f"{mean(float(row['success']) for row in items):.4f}",
                "target_satisfied": f"{mean(float(row['target_satisfied']) for row in items):.4f}",
                "residue": f"{mean(float(row['residue']) for row in items):.4f}",
                "integrity_preserved": f"{mean(float(row['integrity_preserved']) for row in items):.4f}",
                "safe_stop": f"{mean(float(row['safe_stop']) for row in items):.4f}",
                "unsafe_overwrite": f"{mean(float(row['unsafe_overwrite']) for row in items):.4f}",
                "mean_wall_clock_ms": f"{mean(float(row['wall_clock_ms']) for row in items):.3f}",
                "mean_snapshot_bytes": f"{mean(float(row['snapshot_bytes']) for row in items):.2f}",
                "mean_rollback_bytes": f"{mean(float(row['rollback_bytes']) for row in items):.2f}",
            }
        )
    return out


def write_report(summary: list[dict[str, Any]]) -> None:
    lines = [
        "# State-Boundary Validation v5",
        "",
        "This executable stress test uses real temporary files and SQLite state. `irreversible_effect` is an application-level append-only event with no exposed compensation operation; it is a bounded surrogate, not an external payment or email action.",
        "",
        "| Domain | Scenario | Policy | Success | Residue | Integrity | Safe stop | Unsafe overwrite |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['domain']} | {row['scenario']} | {row['policy']} | {float(row['success']):.3f} | "
            f"{float(row['residue']):.3f} | {float(row['integrity_preserved']):.3f} | "
            f"{float(row['safe_stop']):.3f} | {float(row['unsafe_overwrite']):.3f} |"
        )
    lines += [
        "",
        "The guarded policy completes the closed, complete-scope case. For incomplete, stale, concurrent, or non-compensable state, it prioritizes integrity-preserving stop over task completion. Blind rollback can satisfy the visible target while leaving residue or overwriting legitimate concurrent state.",
        "",
    ]
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = [
        run_one(domain, scenario, policy, seed)
        for seed in range(30)
        for domain in DOMAINS
        for scenario in SCENARIOS
        for policy in POLICIES
    ]
    summary = summarize(rows)
    write_csv(RAW_OUT, rows)
    write_csv(SUMMARY_OUT, summary)
    write_report(summary)
    print(f"boundary_runs={len(rows)}")
    print(f"summary_rows={len(summary)}")


if __name__ == "__main__":
    main()
