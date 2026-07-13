# LLM-Agent v4 Semantic-Oracle Audit

Status: PARTIAL DATA RETENTION AFTER PRE-SUBMISSION ORACLE AUDIT

Original endpoint rows: 960.
Audited efficacy rows retained: 552 across 23 tasks.
Audited judge-consistency rows retained: 276.

## Inclusion Rule

Retain only operations whose legacy oracle checked the exact intended object and field (or exact deletion/completion condition) and whose one-action schema could not modify a second field on the same object: web-form edit/status/delete, table update_cell, and workflow complete_step.

## Exclusion Rule

Exclude all file tasks because the legacy snapshot stored content hashes while the oracle checked path existence rather than content provenance. Exclude web-form create tasks because the legacy oracle checked record existence rather than all requested fields. Raw model responses were retained only as hashes, so excluded outcomes cannot be recomputed without a new endpoint run.

## Reproduction Status

The corrected runner now uses semantic-state-v2, exact expected-state construction, and content-preserving rollback. A future endpoint rerun may replace this audited subset with a complete corrected result; until then, only the audited subset is eligible for manuscript efficacy claims.

Excluded task IDs: v4_file_00, v4_file_01, v4_file_02, v4_file_03, v4_file_04, v4_file_05, v4_file_06, v4_file_07, v4_file_08, v4_file_09, v4_file_10, v4_file_11, v4_file_12, v4_file_13, v4_form_02, v4_form_06, v4_form_10
