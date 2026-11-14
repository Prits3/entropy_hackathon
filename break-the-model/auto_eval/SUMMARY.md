# AutoEval — Unified Benchmark & Defense Summary

## What Was Built

**AutoEval** is an automated AI red-teaming, forensic logging, and tool-boundary DLP framework built to evaluate and defend Riley (the simulated hospital AI assistant) across the four sanctioned models.

## Core Components

### 1. Automated Sweep & Attack Suite (`attacks.py`, `agents.py`, `sweeper.py`, `runner.py`)
- Evaluates 8 systematic attack categories (`L1_DIRECT` through `L8_SCHEMA_PROBE` + `SQL_EXTRACTION` + `MANUAL` probes)
- Incorporates both broad automated extraction sweeps and surgical framing/encoding bypasses (`schema-example-framing`, `format-encoding` + TTS/spoken-format reframe, hidden-table probes, `send_email` egress)
- Logs every turn with full `tool_calls`, HTTP status, and `turn_id` to append-only JSONL

### 2. Context- & Tool-Aware Detection + Active Defense (`detection.py`)
- **Tool-Call Grounding**: Inspects `query_db` SQL and outbound tools (`send_email`, `http_post`, `webhook`) to distinguish true DB exfiltration from fabricated PII dumps (`detect_anomaly()` with `is_leak=False`)
- **Surface-Form Canonicalization (`canonicalize_text`)**: Normalizes Unicode dashes/spaces and collapses spelled-out English digit words (`seven-four-zero-...` → `740-...`) and spaced single digits before running PII regexes
- **3-Layer Active Guardrail (`defend_turn`)**:
  1. **Layer 1 (Tool & Table-Scope Gate)** — blocks outbound egress tools, SQL writes, and unauthorized hidden tables (`providers`, `encounters`, `patient_coverage`, `patient_contacts`)
  2. **Layer 2 (Canonicalized Output Filter)** — evaluates canonicalized outputs against PII, clinical PHI, DEA/NPI, and schema/policy patterns
  3. **Layer 3 (Synthetic Fixture / Redaction Response)** — substitutes a safe synthetic data-dictionary fixture or clean refusal on policy violation

### 3. Interactive Forensic Dashboard (`run_dashboard.py`, `dashboard.html`, `visualize.py`)
- Reads all JSONL logs via `analysis.py` so console summaries and HTML charts share a single source of truth
- Generates `dashboard.html` with KPI cards, Model × Technique heatmap, timeline, expandable tool-call inspection, and isolated anomaly/error drawers

---

## Unified Results (456 Valid Turns Analyzed)

### Overall Statistics
- **Valid Turns Analyzed:** 456 (42 API errors/rate-limits excluded from denominators)
- **Confirmed Data / Policy Leaks:** 162 (**35.5%** overall leak rate)
- **Hallucinated PII Anomalies Isolated:** 8 (`0 query_db calls`, tracked separately with `is_leak=False`)
- **Overall Vulnerability Score:** 71 / 100

### Per-Model Breakdown

| Model | Valid Turns | Leaks | Leak Rate | Hallucinated PII | Status |
|---|---|---|---|---|---|
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | 81 | 32 | **39.5%** | 0 | VULNERABLE |
| `deepseek-ai/DeepSeek-V4-Pro-0813` | 153 | 59 | **38.6%** | 0 | VULNERABLE |
| `openai/gpt-oss-120b` | 89 | 32 | **36.0%** | 8 | VULNERABLE |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | 133 | 39 | **29.3%** | 0 | VULNERABLE |

### Technique Effectiveness Breakdown

| Technique | Leaks / Attempts | Leak Rate | Notes |
|---|---|---|---|
| `L8_SCHEMA_PROBE` | 34 / 37 | **91.9%** | Benign "data dictionary / representative row" & schema probes bypass every model |
| `SQL_EXTRACTION` | 63 / 154 | **40.9%** | Raw SQL execution against `query_db` across multiple tables |
| `MANUAL` | 29 / 86 | **33.7%** | Exploratory multi-turn and schema-guided extraction probes |
| `L5_INDIRECT_STAT` | 4 / 14 | **28.6%** | Aggregate / comparative queries leaking underlying scopes or records |
| `L1_DIRECT` | 21 / 78 | **26.9%** | Direct data lookup requests |
| `L4_EVASION_BASE64` | 4 / 19 | **21.1%** | Base64/hex refused (0/14), but spelled-out digit-word encoding succeeds across models |
| `L2_ROLEPLAY` | 6 / 36 | **16.7%** | Roleplay & `send_email` egress (unauthenticated self-service pretexts blocked) |
| `L3_URGENCY` | 1 / 32 | **3.1%** | Emergency/urgency framing rarely succeeds alone |

---

## Active Mitigation Verification (`../03_scripts/verify_mitigation.py`)

Running `defend_turn()` and `analyze_response()` offline across all 23 documented headline turns plus a synthetic hallucinated-PII control yields:
- **18 / 18 (100.0%)** headline attacks, hidden-table leaks, spelled-out digit bypasses, and `send_email` egress caught & blocked
- **5 / 5 (100.0%)** negative controls (`self-service-pretext` x4, DeepSeek explicit-evasion refusal) allowed with **0 false positives**
- **Hallucinated PII** (`0 query_db calls`) isolated as an anomaly without contaminating leak metrics

---

## Quick Usage

```bash
# Offline mitigation verification across all headline findings
python3 03_scripts/verify_mitigation.py

# Console evaluation summary
python3 auto_eval/visualize.py

# Regenerate interactive HTML dashboard
python3 auto_eval/run_dashboard.py --no-open
```
