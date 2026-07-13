# C-SDVR v3 Executable Benchmark Statistical Report

Verification Status: VERIFIED BY RE-RUNNABLE LOCAL CODE

This report summarizes an executable-state benchmark. It is not a live LLM API or real-browser evaluation. Each run mutates an inspectable file-state or SQLite-backed web-form environment.

## Primary Metrics

| Method | Success | Detection F1 | Critical recall | Residue | Token cost | Unnecessary repair | Cost-normalized success |
|---|---:|---:|---:|---:|---:|---:|---:|
| NoCheck | 0.125 | 0.000 | 0.000 | 0.742 | 947.0 | 0.000 | 0.108 |
| FinalVerifier | 0.303 | 0.913 | 0.907 | 0.657 | 2116.3 | 0.034 | 0.130 |
| StepVerifier | 0.125 | 0.913 | 0.907 | 0.742 | 1416.7 | 0.000 | 0.083 |
| ReflectionRetry | 0.744 | 0.913 | 0.907 | 0.216 | 3178.3 | 0.034 | 0.200 |
| C-SDVR-NoRollback | 0.305 | 0.913 | 0.907 | 0.655 | 1959.9 | 0.009 | 0.148 |
| C-SDVR-NoSeverity | 0.727 | 0.913 | 0.907 | 0.179 | 2210.6 | 0.034 | 0.290 |
| C-SDVR | 0.727 | 0.913 | 0.907 | 0.179 | 2039.9 | 0.009 | 0.309 |

## Bootstrap Paired Differences Against C-SDVR

Positive success and cost-normalized differences mean C-SDVR is higher. Negative token differences mean C-SDVR is cheaper.

| Comparator | Success diff | Cost-normalized diff | Token diff |
|---|---:|---:|---:|
| NoCheck | 0.602 [0.570, 0.632] | 0.201 [0.174, 0.225] | 1092.9 [1073.6, 1111.8] |
| FinalVerifier | 0.426 [0.384, 0.466] | 0.180 [0.164, 0.195] | -76.4 [-85.5, -67.5] |
| StepVerifier | 0.602 [0.571, 0.631] | 0.226 [0.209, 0.243] | 623.2 [606.9, 639.1] |
| ReflectionRetry | -0.017 [-0.021, -0.013] | 0.109 [0.104, 0.115] | -1138.5 [-1152.3, -1124.2] |
| C-SDVR-NoRollback | 0.424 [0.381, 0.466] | 0.162 [0.145, 0.179] | 80.0 [80.0, 80.0] |
| C-SDVR-NoSeverity | 0.000 [0.000, 0.000] | 0.019 [0.017, 0.021] | -170.7 [-174.8, -167.0] |

## Sensitivity Analysis

| Sensitivity factor | C-SDVR success | C-SDVR cost-normalized success | C-SDVR token cost |
|---:|---:|---:|---:|
| 0.80 | 0.509 | 0.223 | 1955.1 |
| 0.90 | 0.615 | 0.265 | 2000.3 |
| 1.00 | 0.734 | 0.312 | 2041.2 |
| 1.10 | 0.858 | 0.361 | 2078.7 |
| 1.20 | 0.931 | 0.390 | 2081.9 |

## Statistical Fallacy Scan

| Fallacy | Status | Note |
|---|---|---|
| Simulation-as-real-world fallacy | PASS | Manuscript must state this is an executable prototype benchmark, not live LLM/browser evaluation. |
| Accuracy-only fallacy | PASS | Cost, latency, unnecessary repair, and residue are reported. |
| Selective reporting | PASS | NoRollback and NoSeverity ablations are included. |
| Parameter fragility | PARTIAL | Sensitivity factors are reported; future live-agent traces are still needed. |
| External validity drift | WARN | File and form environments do not cover unrestricted web browsing or irreversible APIs. |
| Multiple-comparison overclaim | PASS | Bootstrap intervals are descriptive; avoid formal superiority claims beyond this benchmark. |
| Causal overclaim | PASS if preserved | Results compare policies under controlled executable traces, not deployed causal effects. |
