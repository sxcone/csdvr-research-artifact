# Browser Validation Report

Verification Status: VERIFIED BY LOCAL FLASK/SQLITE AND HEADLESS CHROMIUM VIA PLAYWRIGHT

This validation uses a real headless Chromium browser to open a local HTML form, fill fields, click submit, and then checks the backing SQLite state. It is a browser-execution validation, not a live LLM-agent validation.

| Method | Success | Residue | Detection F1 | Critical recall | Token cost | CNS |
|---|---:|---:|---:|---:|---:|---:|
| NoCheck | 0.000 | 0.783 | 0.000 | 0.000 | 720.0 | 0.000 |
| FinalVerifier | 0.362 | 0.638 | 1.000 | 1.000 | 2127.3 | 0.148 |
| C-SDVR | 1.000 | 0.000 | 1.000 | 1.000 | 2124.1 | 0.424 |
