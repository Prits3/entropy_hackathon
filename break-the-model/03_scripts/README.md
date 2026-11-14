# 03_scripts — reproduction scripts

Each uses the challenge client (`btm.py` from the starter kit). Run from the **starter-kit
repo root** (where `btm.py` and `.env` live), e.g. `.venv\Scripts\python <script> [model]`.
All are read-only/non-destructive unless noted.

## Attack / leak probes
| Script | What it does |
|---|---|
| `probe_single_leak.py` | Three single-turn bypasses (encoding, self-service, schema-example) vs. one model. |
| `probe_schema.py` | Read-only schema recon: list tables, patients schema, staff table, sensitive columns. |
| `probe_hidden_tables.py` | One representative row from each sensitive hidden table. |
| `probe_email_egress.py` | Egress demo: Riley's `send_email` tool, self-directed to the on-file address only. |
| `probe_write_capability.py` | Non-destructive: asks what write access exists. **No write is executed.** |

## Validators (no attacks; `validate_capture.py` needs no network)
| Script | What it does |
|---|---|
| `validate_capture.py` | Consistency + synthetic-data check on the captured dataset. |
| `validate_cross_model.py` | Cross-model agreement on sampled patient slices. |
| `validate_hidden_cross_model.py` | Cross-model agreement on the hidden sensitive tables. |

Outputs land in the starter kit's `logs/`; the committed copies are in
[`../02_validation/`](../02_validation/) and [`../04_data/`](../04_data/).
