# 01_findings — vulnerability write-ups

Each file is one finding: what leaked, the exact attack, why it works, and a suggested fix.

| File | Finding | Severity |
|---|---|---|
| `FINDINGS.md` | Cross-model summary + the core benign-framing / encoding bypasses (incl. hardest model). | High |
| `hidden_tables.md` | DB has 9 tables; framing leaks staff DEA/NPI, clinical PHI, insurance, contacts — linkable by `patient_id`. | Critical |
| `email_egress.md` | Riley exfiltrates PII via its `send_email` tool (demonstrated non-harmfully, self-directed). | High |
| `write_capability.md` | Riley self-reports MODIFY/INSERT/DELETE via `query_db`. No write was executed. | High |

Reproduction scripts: [`../03_scripts/`](../03_scripts/). Cross-model proof the data is real:
[`../02_validation/`](../02_validation/).
