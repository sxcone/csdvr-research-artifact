# LLM-Agent Validation Report

Verification Status: SMOKE TEST

This validation uses real model calls to produce JSON actions for temporary filesystem tasks and Playwright-submitted local web-form tasks. It remains bounded to local reversible tasks and is not an open-world browser-agent evaluation.

| Method | Runs | Success | Residue | Detection F1 | Critical recall | Rollback use | Repair calls | Invalid JSON rate | Token cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C-SDVR | 2 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 371.0 |
