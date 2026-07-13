# Postcondition Generation Study v4

Expected generation rows under available models: 160
Model B available: True

| Model | Items | Object acc. | Field acc. | Constraint acc. | Forbidden recall | Strict err. | Invalid JSON | Token |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek-v4-flash | 80 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 342.5 |
| deepseek-v4-pro | 80 | 0.988 | 0.988 | 0.988 | 0.988 | 0.013 | 0.013 | 584.5 |

## Executable downstream C-SDVR validation

The downstream study replays paired agent errors against mutable structured states; recovery decisions are executed before comparison with a gold final state.

| Model | PC mode | Runs | Success | Residue | False repair | Unnecessary repair |
|---|---|---:|---:|---:|---:|---:|
| deepseek-v4-flash | Gold-PC | 400 | 1.000 | 0.000 | 0.000 | 0.000 |
| deepseek-v4-flash | LLM-PC | 400 | 1.000 | 0.000 | 0.000 | 0.000 |
| deepseek-v4-flash | WrongTarget-PC | 400 | 0.000 | 1.000 | 0.150 | 0.150 |
| deepseek-v4-pro | Gold-PC | 400 | 1.000 | 0.000 | 0.000 | 0.000 |
| deepseek-v4-pro | LLM-PC | 400 | 0.988 | 0.013 | 0.000 | 0.000 |
| deepseek-v4-pro | WrongTarget-PC | 400 | 0.000 | 1.000 | 0.237 | 0.237 |
