# Postcondition Generation Study v4

Expected generation rows under available models: 80
Smoke mode: 2 model(s) exercised

| Model | Items | Object acc. | Field acc. | Constraint acc. | Forbidden recall | Strict err. | Invalid JSON | Token |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek-v4-flash | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 304.5 |
| deepseek-v4-pro | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 433.5 |

## Executable downstream C-SDVR validation

The downstream study replays paired agent errors against mutable structured states; recovery decisions are executed before comparison with a gold final state.

| Model | PC mode | Runs | Success | Residue | False repair | Unnecessary repair |
|---|---|---:|---:|---:|---:|---:|
| deepseek-v4-flash | Gold-PC | 20 | 1.000 | 0.000 | 0.000 | 0.000 |
| deepseek-v4-flash | LLM-PC | 20 | 1.000 | 0.000 | 0.000 | 0.000 |
| deepseek-v4-flash | WrongTarget-PC | 20 | 0.000 | 1.000 | 0.200 | 0.200 |
| deepseek-v4-pro | Gold-PC | 20 | 1.000 | 0.000 | 0.000 | 0.000 |
| deepseek-v4-pro | LLM-PC | 20 | 1.000 | 0.000 | 0.000 | 0.000 |
| deepseek-v4-pro | WrongTarget-PC | 20 | 0.000 | 1.000 | 0.400 | 0.400 |
