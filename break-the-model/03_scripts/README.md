# 03_scripts — reproduction & verification scripts

Run from the `break-the-model/` root (where `btm.py` and `.env` live), e.g. `python3 03_scripts/<script>`.
Offline scripts require no API key or network access; live probes use `btm.py` (`POST /chat` only).

## Offline Validation & Defense Verification (No Network)
| Script | What it does |
|---|---|
| `verify_mitigation.py` | Verifies `detection.analyze_response()` and `detection.defend_turn()` against all 23 headline turns + hallucinated PII (`18/18` attacks blocked, `0` false positives). |
| `validate_capture.py` | Consistency + synthetic-data check on `04_data/patients_captured.json` (343 records, `example.*` check). |

## Attack / Leak Probes (Live `/chat` API)
| Script | What it does |
|---|---|
| `probe_single_leak.py` | Three single-turn bypasses (encoding, self-service, schema-example) vs. one model. |
| `probe_schema.py` | Read-only schema recon: list tables, patients schema, staff table, sensitive columns. |
| `probe_hidden_tables.py` | One representative row from each sensitive hidden table. |
| `probe_email_egress.py` | Egress demo: Riley's `send_email` tool, self-directed to the on-file address only. |
| `probe_write_capability.py` | Non-destructive: asks what write access exists. **No write is executed.** |
| `full_extraction.py` | Automated multi-technique SQL extraction sweep against `Qwen3-235B`. |
| `deep_extraction.py` | Schema-informed extraction across all 9 allowed tables. |
| `targeted_extraction.py` | Column-targeted SQL extraction queries. |
| `final_extraction.py` | Follow-up extraction queries filling schema gaps. |

## Cross-Model Validators (Live `/chat` API)
| Script | What it does |
|---|---|
| `validate_cross_model.py` | Cross-model agreement on sampled patient slices. |
| `validate_hidden_cross_model.py` | Cross-model agreement on the hidden sensitive tables. |

Committed outputs live in [`../02_validation/`](../02_validation/), [`../04_data/`](../04_data/), and [`../logs/`](../logs/).
