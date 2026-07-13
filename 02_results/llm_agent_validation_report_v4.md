# LLM-Agent Validation v4

Observed main rows: 960
Expected rows under available models: 960
Model B unavailable: False
Oracle version: semantic-state-v2
Action prompt version: action-json-v5.1
Sampling temperature: 0.2
Thinking mode: disabled
Raw synthetic-task responses, parsed actions, state snapshots, prompt hashes, endpoint host, and timing are retained in the CSV/JSONL trace outputs. API keys are never written.

| Model | Policy | Runs | Success | Residue | Repair trig. | Rollback trig. | Invalid JSON | Invalid judge | Judge false success | Token |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek-v4-flash | C-SDVR | 80 | 1.000 | 0.000 | 0.062 | 0.000 | 0.000 | 0.000 | 0.000 | 1045.9 |
| deepseek-v4-flash | FinalVerifier | 80 | 1.000 | 0.000 | 0.062 | 0.000 | 0.000 | 0.000 | 0.000 | 1050.0 |
| deepseek-v4-flash | LLMJudgeFinal | 80 | 0.887 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.013 | 2078.0 |
| deepseek-v4-flash | LLMJudgeRetry | 80 | 0.963 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.013 | 2108.0 |
| deepseek-v4-flash | LLMJudgeStep | 80 | 0.975 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 2078.2 |
| deepseek-v4-flash | NoCheck | 80 | 0.925 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1017.3 |
| deepseek-v4-pro | C-SDVR | 80 | 1.000 | 0.000 | 0.025 | 0.000 | 0.000 | 0.000 | 0.000 | 1025.9 |
| deepseek-v4-pro | FinalVerifier | 80 | 1.000 | 0.000 | 0.013 | 0.000 | 0.000 | 0.000 | 0.000 | 1020.8 |
| deepseek-v4-pro | LLMJudgeFinal | 80 | 0.975 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.025 | 2073.0 |
| deepseek-v4-pro | LLMJudgeRetry | 80 | 0.975 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.025 | 2073.2 |
| deepseek-v4-pro | LLMJudgeStep | 80 | 0.988 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.013 | 2073.0 |
| deepseek-v4-pro | NoCheck | 80 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1014.4 |
