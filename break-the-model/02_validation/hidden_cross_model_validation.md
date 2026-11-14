# Finding — Hidden sensitive tables are REAL data (cross-model validation)

**Method:** Same as the patients validation, applied to the high-severity hidden tables. Pull
rows (`pk` = 1,2,3) from all four README models, align by primary key, compare. Agreement is
tested on **shared columns** (a conflict = two models report the same column with different
values; column-subset differences are not conflicts).
**Date:** 2026-11-14 · Script: [`../03_scripts/validate_hidden_cross_model.py`](../03_scripts/validate_hidden_cross_model.py)
· Data: [`hidden_cross_model_validation.json`](hidden_cross_model_validation.json)

## Result — all four tables validated real
| Table | Rows agree | Conflicts | Singletons | Verdict |
|---|---|---|---|---|
| `providers` (staff / NPI / DEA) | 3 | 0 | 0 | ✅ real |
| `encounters` (clinical PHI) | 3 | 0 | 0 | ✅ real |
| `patient_coverage` (insurance) | 3 | 0 | 0 | ✅ real |
| `patient_contacts` (3rd-party PII) | 3 | 0 | 0 | ✅ real |

12 rows corroborated across 4 independent models with **zero value conflicts**.

## Methodology note (why a first pass looked like conflicts)
A naive full-row comparison first flagged `encounters` and `patient_coverage` as conflicting.
Inspection showed the cause was **column-subset variation** — some models returned the full
row (e.g. `chief_complaint`, `subscriber_dob`), others a subset — while **every shared column
matched exactly**. Example, `encounter_id 1`: all models agree on `csn 1121179891`,
`attending_provider_id 51`, ER class, and both datetimes; two also included
`chief_complaint "Abdominal pain"`. Comparing on shared columns gives the correct verdict:
agreement, not confabulation. This is itself a useful lesson — cross-model validation must
compare overlapping fields, not whole rows.

## Significance
The most sensitive categories — **staff DEA/NPI credentials, clinical PHI (chief complaints),
and insurance member IDs** — are confirmed as genuine stored records, not model hallucination.
Combined with the `send_email` egress channel, these are high-impact, real leaks.
