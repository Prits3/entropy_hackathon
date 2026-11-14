# Logging System Enhancement Summary

## What Was Enhanced

This document summarizes the comprehensive logging improvements made to AutoEval v2.0+ for better evaluation, debugging, and reproducibility.

---

## Core Improvements

### 1. **Enhanced Turn-Level Logging** (`eval_turns.jsonl`)

Added to every API request/response:
- `http_status` — HTTP response code for error tracking
- `raw_response_length` — Response size in bytes (performance metric)
- `api_endpoint` — Full endpoint path for reproducibility
- Complete request/response payloads preserved

**Benefit:** Can trace exactly what was sent/received, crucial for debugging false positives/negatives.

### 2. **Rich Result Metadata** (`sweeper_results.jsonl`)

Each test result now includes:
- Progress tracking: `current/total`, `progress_percent`
- Batch configuration: `batch_size`, `model_idx`
- Multi-turn support: `turn_num`, `total_turns`, `parent_test_id`
- Detection metrics: `confidence` score, `leak_type` classification

**Benefit:** Can analyze which techniques work best, spot patterns in successful attacks, track sweep progress accurately.

### 3. **Sweep Configuration Header** (`sweeper_header.jsonl`)

Captured before each sweep:
- Models being tested (count)
- Techniques included/excluded
- Batch size configuration
- Test count breakdown by technique

**Benefit:** Verify exact test conditions for fair comparisons between runs.

### 4. **Training Cycle Analysis** (`trainer_analysis.jsonl`, `trainer_comprehensive.jsonl`)

Per-cycle deep analysis including:
- Per-technique success rates and leak types
- Identified improvement opportunities
- Sample successful/failed attack prompts
- Leak distribution statistics

**Benefit:** Understand why certain techniques are more effective, guide future attack development.

### 5. **Comprehensive Schema Documentation** (`log_schema.md`)

Complete reference for all log fields, examples, and usage patterns.

---

## New Tools & Features

### Validation Script
- `python3 auto_eval/test_logging.py` — Validates JSON structure and required fields
- Checks file integrity after sweeps
- Reports size, line counts, and latest timestamps

### Dashboard Enhancements
- Vulnerability trend indicator (increasing/decreasing/stable)
- Pie chart showing leak distribution by technique
- `/api/data` endpoint for live data consumption
- Real-time feed information embedded in HTML

### Schema Documentation
- `log_schema.md` — Complete field reference with examples
- `LOGGING_GUIDE.md` — Usage patterns, debugging tips, retention policies

---

## File Structure

```
auto_eval/logs/
├── eval_turns.jsonl              # Every API turn (append-only)
├── sweeper_results.jsonl         # Test outcomes with metadata
├── sweeper_header.jsonl          # Sweep configuration per run
├── trainer_analysis.jsonl        # Technique stats & opportunities
├── trainer_comprehensive.jsonl   # Deep analysis reports
├── improvements.json             # Historical training history
├── dashboard.html                # Generated interactive dashboard
├── log_schema.md                 # Field reference documentation
└── LOGGING_GUIDE.md              # User-facing logging guide
```

---

## Data Flow Example

```
1. Sweep starts → Write sweeper_header.jsonl (config)
2. Send attack prompt → Write eval_turns.jsonl (request/response)
3. Analyze response → Write sweeper_results.jsonl (outcome + metadata)
4. Training cycle → Write trainer_analysis.jsonl (stats)
5. Training complete → Write trainer_comprehensive.jsonl (deep analysis)
6. Dashboard refresh → Reads all logs, generates HTML visualization
```

---

## Key Metrics Captured

| Metric | Source File | Use Case |
|--------|-------------|----------|
| Leak rate by model | `sweeper_results.jsonl` | Identify vulnerable models |
| Technique effectiveness | `trainer_comprehensive.jsonl` | Prioritize attack development |
| API error rates | `eval_turns.jsonl` (http_status) | Monitor backend health |
| Response sizes | `eval_turns.jsonl` (raw_response_length) | Performance analysis |
| Trend direction | Dashboard computation | Early warning for vulnerability drift |

---

## Best Practices

1. **Never edit logs in-place** — All files are append-only
2. **Keep eval_turns.jsonl indefinitely** — Critical for debugging
3. **Archive sweeper_results.jsonl monthly** — Still valuable for trend analysis
4. **Use test_logging.py after each sweep** — Verify integrity quickly
5. **Monitor log growth** — Set alerts if files exceed expected size

---

## Next Steps

1. ✅ Review `log_schema.md` for complete field documentation
2. ✅ Run `python3 test_logging.py` to validate your logs
3. 📊 Explore the dashboard: `python3 dashboard.py --live`
4. 🔗 Integrate `/api/data` endpoint into your monitoring pipeline

---

**Version:** 2.0+  
**Last Updated:** November 14, 2026  
**Maintained By:** AutoEval Team
