# State-Boundary Validation v5

This executable stress test uses real temporary files and SQLite state. `irreversible_effect` is an application-level append-only event with no exposed compensation operation; it is a bounded surrogate, not an external payment or email action.

| Domain | Scenario | Policy | Success | Residue | Integrity | Safe stop | Unsafe overwrite |
|---|---|---|---:|---:|---:|---:|---:|
| file | complete_scope | BlindRollback | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| file | complete_scope | C-SDVR-Guarded | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| file | concurrent_modification | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 |
| file | concurrent_modification | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| file | irreversible_effect | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |
| file | irreversible_effect | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| file | scope_omission | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |
| file | scope_omission | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| file | stale_snapshot | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 |
| file | stale_snapshot | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| sqlite_form | complete_scope | BlindRollback | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| sqlite_form | complete_scope | C-SDVR-Guarded | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| sqlite_form | concurrent_modification | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 |
| sqlite_form | concurrent_modification | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| sqlite_form | irreversible_effect | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |
| sqlite_form | irreversible_effect | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| sqlite_form | scope_omission | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |
| sqlite_form | scope_omission | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |
| sqlite_form | stale_snapshot | BlindRollback | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 |
| sqlite_form | stale_snapshot | C-SDVR-Guarded | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 |

The guarded policy completes the closed, complete-scope case. For incomplete, stale, concurrent, or non-compensable state, it prioritizes integrity-preserving stop over task completion. Blind rollback can satisfy the visible target while leaving residue or overwriting legitimate concurrent state.
