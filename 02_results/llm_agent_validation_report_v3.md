# LLM-Agent Validation Report

Verification Status: VERIFIED WITH OPENAI-COMPATIBLE LLM ENDPOINT

This validation uses real model calls to produce JSON actions for temporary filesystem tasks and Playwright-submitted local web-form tasks. It remains bounded to local reversible tasks and is not an open-world browser-agent evaluation.

| Method | Runs | Success | Residue | Detection F1 | Critical recall | Rollback use | Repair calls | Invalid JSON rate | Token cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NoCheck | 60 | 0.933 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.117 | 462.8 |
| FinalVerifier | 60 | 0.950 | 0.017 | 1.000 | 0.000 | 0.000 | 0.050 | 0.117 | 564.0 |
| C-SDVR | 60 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.133 | 434.4 |
