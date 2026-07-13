# ASE Paired Task-Cluster Contrasts v6

Positive values favor C-SDVR-LLMRepair. Intervals use 10,000 paired bootstrap resamples over 40 task clusters; the six model/repeat trajectories within each task are averaged before resampling.

| Baseline | Effect | Estimate | 95% task-cluster CI |
|---|---|---:|---:|
| NoCheck | success difference | 0.0708 | [0.0250, 0.1333] |
| NoCheck | residue reduction | 0.0375 | [0.0083, 0.0750] |
| NoCheck | integrity-outcome difference | 0.0875 | [0.0292, 0.1583] |
| NoCheck | token saving | -81.0333 | [-156.6917, -24.2583] |
| FinalReplay | success difference | 0.0375 | [0.0000, 0.0958] |
| FinalReplay | residue reduction | 0.0167 | [0.0000, 0.0375] |
| FinalReplay | integrity-outcome difference | 0.0542 | [0.0083, 0.1167] |
| FinalReplay | token saving | -16.3083 | [-40.9500, 1.9500] |
| JudgeRepair | success difference | 0.0833 | [0.0292, 0.1500] |
| JudgeRepair | residue reduction | 0.0542 | [0.0167, 0.1042] |
| JudgeRepair | integrity-outcome difference | 0.1000 | [0.0375, 0.1750] |
| JudgeRepair | token saving | 674.1083 | [560.5917, 799.5792] |
| C-SDVR-OracleUpperBound | success difference | -0.0167 | [-0.0458, 0.0000] |
| C-SDVR-OracleUpperBound | residue reduction | 0.0000 | [0.0000, 0.0000] |
| C-SDVR-OracleUpperBound | integrity-outcome difference | 0.0000 | [0.0000, 0.0000] |
| C-SDVR-OracleUpperBound | token saving | -81.0333 | [-155.3333, -24.4292] |
