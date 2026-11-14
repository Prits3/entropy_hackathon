# 02_validation — is the leaked data real or hallucination?

Method: pull the **same** rows from all four README models and align them. Independent models
returning byte-identical rows = genuine stored data, not per-model confabulation. Agreement is
tested on **shared columns** (column-subset differences are not conflicts).

| File | Contents |
|---|---|
| `cross_model_validation.md` | Patients table: 39 rows agree, **0 conflicts** across 4 models. |
| `cross_model_validation.json` | The corroborated patient rows + agreement levels. |
| `hidden_cross_model_validation.md` | Hidden tables (providers/encounters/coverage/contacts): all agree, **0 conflicts**. |
| `hidden_cross_model_validation.json` | The corroborated hidden-table rows. |

Verdict: both patient data and the sensitive hidden-table data (staff DEA/NPI, clinical PHI,
insurance IDs) are confirmed **real**. Validators: [`../03_scripts/`](../03_scripts/).
