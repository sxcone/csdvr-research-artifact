# SQJ Major-Revision Quantitative Analyses

## Denominator Transparency

The main controlled benchmark has fault prevalence 0.7248. C-SDVR all-run success is 0.8019; fault-conditioned recovery success is 0.7267. Mean all-run and fault-only token proxies are 2039.88 and 2197.69.

## Capability Grid

The independent 4 x 4 x 4 grid contains 64 capability combinations. At detector=0.90, repair=0.78, and rollback=0.92, fault-conditioned success is 0.7259 and residue is 0.1835.

The three values are design-point capabilities for studying controller structure. They are not estimates of deployed component accuracy. Closed-scope live/browser repair is oracle-like and is reported as an upper-bound diagnostic rather than calibration evidence.

## Measured Costs

Wall-clock time, serialized snapshot size, and changed rollback payload are measured directly for the local file/SQLite and Chromium/SQLite runs. Values remain machine- and implementation-specific and do not include external API billing or human confirmation.

## Calibration Rows

| Source | Domain | Detector | Repair | Rollback | Interpretation |
|---|---|---:|---:|---:|---|
| controlled_design_point | pooled | 0.9000 | 0.7800 | 0.9200 | pre-registered imperfect-component design point; not fitted to deployment data |
| live_closed_scope | file | 1.0000 | 1.0000 | 1.0000 | oracle-like scripted recovery under complete local scope; upper-bound diagnostic |
| live_closed_scope | form | 1.0000 | 1.0000 | 1.0000 | oracle-like scripted recovery under complete local scope; upper-bound diagnostic |
| browser_closed_scope | browser_form | 1.0000 | 1.0000 | 1.0000 | oracle-like scripted recovery under complete local scope; upper-bound diagnostic |

## Output Files

- `all_run_fault_conditioned_metrics_v5.csv`
- `deviation_class_outcomes_v5.csv`
- `capability_grid_summary_v5.csv`
- `capability_grid_by_deviation_v5.csv`
- `capability_calibration_v5.csv`
- `measured_execution_costs_v5.csv`
- `figures/capability_grid_v5.pdf`
