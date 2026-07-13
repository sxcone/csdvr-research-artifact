# Live-style Validation Report

Verification Status: VERIFIED BY LOCAL FILESYSTEM AND FLASK HTTP EXECUTION

This validation uses real temporary filesystem mutations and a local Flask HTTP form service backed by SQLite. It is not a live LLM API or real-browser Playwright experiment because `npx` is unavailable in the current environment.

| Method | Success | Residue | Detection F1 | Critical recall | Token cost | CNS |
|---|---:|---:|---:|---:|---:|---:|
| NoCheck | 0.000 | 0.777 | 0.000 | 0.000 | 700.0 | 0.000 |
| FinalVerifier | 0.324 | 0.676 | 1.000 | 1.000 | 2086.2 | 0.141 |
| C-SDVR | 1.000 | 0.000 | 1.000 | 1.000 | 2064.2 | 0.454 |
