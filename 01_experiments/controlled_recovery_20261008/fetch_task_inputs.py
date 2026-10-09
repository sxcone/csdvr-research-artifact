#!/usr/bin/env python3
"""Fetch pinned public YoloFS task inputs without rehosting their source files."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "yolofs_extended_task_inputs_gitblob_manifest_20261007.json"
TASKS = HERE / "tasks_opaque"
BASE = "https://raw.githubusercontent.com/YoloFS/agent-eval"

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commit = manifest["repository_commit"]
    for task in manifest["tasks"]:
        for item in task["files"]:
            rel = Path(task["task"]) / Path(item["path"])
            url = f"{BASE}/{commit}/tasks_opaque/{rel.as_posix()}"
            with urlopen(url, timeout=30) as response:
                content = response.read()
            if sha256(content) != item["sha256"]:
                raise RuntimeError(f"SHA-256 mismatch for {rel.as_posix()}")
            target = TASKS / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print(f"Fetched and verified {sum(len(t['files']) for t in manifest['tasks'])} files from {commit}.")

if __name__ == "__main__":
    main()
