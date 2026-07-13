# ASE Revision Numeric Audit v6

Checks: 52
Failures: 0

## Aggregate autonomous-repair metrics

| Policy | N | Final success | Final residue | Integrity outcome | Safe stop | Conditional repair success | Residue recovered | Mean tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C-SDVR-LLMRepair | 240 | 0.983 | 0.000 | 1.000 | 0.017 | 0.810 | 9/9 | 578.9 |
| C-SDVR-OracleUpperBound | 240 | 1.000 | 0.000 | 1.000 | 0.000 | 1.000 | 9/9 | 497.9 |
| FinalReplay | 240 | 0.946 | 0.017 | 0.946 | 0.000 | 0.381 | 5/9 | 562.6 |
| JudgeRepair | 240 | 0.900 | 0.054 | 0.900 | 0.000 | 0.095 | 1/9 | 1253.0 |
| NoCheck | 240 | 0.912 | 0.037 | 0.912 | 0.000 | 0.000 | 0/9 | 497.9 |

## Checks

- PASS: autonomous row count (observed=1200, expected=1200)
- PASS: policy count (observed=['C-SDVR-LLMRepair', 'C-SDVR-OracleUpperBound', 'FinalReplay', 'JudgeRepair', 'NoCheck'])
- PASS: model count (observed=['deepseek-v4-flash', 'deepseek-v4-pro'])
- PASS: task count (observed=40)
- PASS: repeat indices (observed=[0, 1, 2])
- PASS: trajectory count (observed=240)
- PASS: five policy replays per trajectory (each trajectory must contain every policy exactly once)
- PASS: shared initial action per trajectory (initial action hashes are identical across policy replay rows)
- PASS: shared post-action state per trajectory (post-action state hashes are identical across policy replay rows)
- PASS: shared initial outcomes per trajectory (initial success, residue, and taxonomy labels are policy invariant)
- PASS: natural initial failures (observed=21, expected=21)
- PASS: natural residue trajectories (observed=9, expected=9)
- PASS: no invalid initial JSON (all initial action objects passed JSON/schema parsing)
- PASS: balanced model-policy cells (cells={('deepseek-v4-flash', 'C-SDVR-LLMRepair'): 120, ('deepseek-v4-flash', 'C-SDVR-OracleUpperBound'): 120, ('deepseek-v4-flash', 'FinalReplay'): 120, ('deepseek-v4-flash', 'JudgeRepair'): 120, ('deepseek-v4-flash', 'NoCheck'): 120, ('deepseek-v4-pro', 'C-SDVR-LLMRepair'): 120, ('deepseek-v4-pro', 'C-SDVR-OracleUpperBound'): 120, ('deepseek-v4-pro', 'FinalReplay'): 120, ('deepseek-v4-pro', 'JudgeRepair'): 120, ('deepseek-v4-pro', 'NoCheck'): 120})
- PASS: aggregate counts: C-SDVR-LLMRepair (observed=(236, 0, 240, 4, 17))
- PASS: aggregate counts: C-SDVR-OracleUpperBound (observed=(240, 0, 240, 0, 21))
- PASS: aggregate counts: FinalReplay (observed=(227, 4, 227, 0, 8))
- PASS: aggregate counts: JudgeRepair (observed=(216, 13, 216, 0, 17))
- PASS: aggregate counts: NoCheck (observed=(219, 9, 219, 0, 0))
- PASS: model-policy summary rows (observed=10)
- PASS: summary success/residue: deepseek-v4-flash C-SDVR-LLMRepair (recomputed=(1.000000000000,0.000000000000))
- PASS: summary success/residue: deepseek-v4-flash C-SDVR-OracleUpperBound (recomputed=(1.000000000000,0.000000000000))
- PASS: summary success/residue: deepseek-v4-flash FinalReplay (recomputed=(0.958333333333,0.008333333333))
- PASS: summary success/residue: deepseek-v4-flash JudgeRepair (recomputed=(0.925000000000,0.033333333333))
- PASS: summary success/residue: deepseek-v4-flash NoCheck (recomputed=(0.933333333333,0.025000000000))
- PASS: summary success/residue: deepseek-v4-pro C-SDVR-LLMRepair (recomputed=(0.966666666667,0.000000000000))
- PASS: summary success/residue: deepseek-v4-pro C-SDVR-OracleUpperBound (recomputed=(1.000000000000,0.000000000000))
- PASS: summary success/residue: deepseek-v4-pro FinalReplay (recomputed=(0.933333333333,0.025000000000))
- PASS: summary success/residue: deepseek-v4-pro JudgeRepair (recomputed=(0.875000000000,0.075000000000))
- PASS: summary success/residue: deepseek-v4-pro NoCheck (recomputed=(0.891666666667,0.050000000000))
- PASS: scalability row count (observed=192, expected=192)
- PASS: scalability design cells (4 repository sizes x 2 file sizes x 3 mutation widths)
- PASS: scalability repeats (eight repeats per design cell)
- PASS: scalability verification integrity (all exact-diff and clean-Git rollback assertions passed)
- PASS: paired contrast row count (observed=16, expected=16)
- PASS: paired contrast design (40 task clusters, 240 paired trajectories, and 10,000 resamples per contrast)
- PASS: paired contrast estimate: NoCheck final_success (observed=0.07083333333333333, expected=0.07083333333333333)
- PASS: paired contrast estimate: NoCheck final_residue (observed=0.0375, expected=0.0375)
- PASS: paired contrast estimate: NoCheck integrity_preserving_outcome (observed=0.0875, expected=0.0875)
- PASS: paired contrast estimate: NoCheck token_cost (observed=-81.03333333333333, expected=-81.03333333333333)
- PASS: paired contrast estimate: FinalReplay final_success (observed=0.0375, expected=0.0375)
- PASS: paired contrast estimate: FinalReplay final_residue (observed=0.016666666666666666, expected=0.016666666666666666)
- PASS: paired contrast estimate: FinalReplay integrity_preserving_outcome (observed=0.05416666666666666, expected=0.05416666666666667)
- PASS: paired contrast estimate: FinalReplay token_cost (observed=-16.30833333333333, expected=-16.308333333333334)
- PASS: paired contrast estimate: JudgeRepair final_success (observed=0.08333333333333333, expected=0.08333333333333333)
- PASS: paired contrast estimate: JudgeRepair final_residue (observed=0.05416666666666666, expected=0.05416666666666667)
- PASS: paired contrast estimate: JudgeRepair integrity_preserving_outcome (observed=0.1, expected=0.1)
- PASS: paired contrast estimate: JudgeRepair token_cost (observed=674.1083333333333, expected=674.1083333333333)
- PASS: paired contrast estimate: C-SDVR-OracleUpperBound final_success (observed=-0.016666666666666666, expected=-0.016666666666666666)
- PASS: paired contrast estimate: C-SDVR-OracleUpperBound final_residue (observed=0.0, expected=0.0)
- PASS: paired contrast estimate: C-SDVR-OracleUpperBound integrity_preserving_outcome (observed=0.0, expected=0.0)
- PASS: paired contrast estimate: C-SDVR-OracleUpperBound token_cost (observed=-81.03333333333333, expected=-81.03333333333333)
