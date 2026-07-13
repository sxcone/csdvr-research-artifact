# LLM-Agent Validation v4

Observed main rows: 12
Expected rows under available models: 480
Smoke mode: 2 model(s) exercised
Oracle version: semantic-state-v2
Action prompt version: action-json-v5.1
Sampling temperature: 0.2
Thinking mode: disabled
Raw synthetic-task responses, parsed actions, state snapshots, prompt hashes, endpoint host, and timing are retained in the CSV/JSONL trace outputs. API keys are never written.

| Model | Policy | Runs | Success | Residue | Repair trig. | Rollback trig. | Invalid JSON | Invalid judge | Judge false success | Token |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek-v4-flash | LLMJudgeFinal | 2 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 633.5 |
| deepseek-v4-flash | LLMJudgeRetry | 2 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 633.0 |
| deepseek-v4-flash | NoCheck | 2 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 297.0 |
| deepseek-v4-pro | LLMJudgeFinal | 2 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 629.0 |
| deepseek-v4-pro | LLMJudgeRetry | 2 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 629.0 |
| deepseek-v4-pro | NoCheck | 2 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 291.5 |
