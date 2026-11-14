# Logging and Monitoring Guide

This guide explains the comprehensive logging system built into AutoEval for evaluation, debugging, reproducibility, and continuous monitoring.

## Overview

AutoEval captures **everything** needed to:
- 🔍 Debug failed attacks or false positives
- 📊 Reproduce exact test conditions
- 📈 Monitor vulnerability trends over time
- 🔗 Correlate events across sweeps and training cycles

All logs are stored in JSONL (JSON Lines) format — one structured JSON object per line, append-only, human-readable, machine-parsable.

---

## Log Files Reference

### Core Logs (Always Written)

| File | Purpose | When Written |
|------|---------|--------------|
| `eval_turns.jsonl` | Every API request/response | Per turn during sweep |
| `sweeper_results.jsonl` | Test outcomes with metadata | Per test result |
| `sweeper_header.jsonl` | Sweep configuration | Before each sweep starts |

### Training Cycle Logs

| File | Purpose | When Written |
|------|---------|--------------|
| `trainer_analysis.jsonl` | Technique stats & opportunities | During training cycle |
| `trainer_comprehensive.jsonl` | Deep analysis reports | At end of training |
| `improvements.json` | Historical improvement tracking | Every training cycle |

### Dashboard Logs

| File | Purpose | When Written |
|------|---------|--------------|
| `dashboard.html` | Interactive visualization | On generation/refresh |

---

## Key Logging Enhancements (v2.0+)

### 1. Full Request/Response Capture

Every API call now logs:
- Complete request payload (participant, model, conversation_id, message)
- Full parsed response (turn_id, reply, tool_calls)
- HTTP metadata (status code, response size)
- Correlation IDs for tracing across multiple calls

**Use case:** Reproduce a specific interaction that triggered an attack or false positive.

### 2. Rich Test Metadata

Each result includes contextual metadata:
- Batch progress (`current/total`, `progress_percent`)
- Model index in sweep order
- Multi-turn test tracking with parent references
- Technique and leak type classification

**Use case:** Analyze which techniques work best, spot patterns in successful attacks.

### 3. Sweep Configuration Logging

Before each sweep, the system logs:
- Models being tested
- Techniques included/excluded
- Batch size configuration
- Test count breakdown by technique

**Use case:** Verify you're running the exact same test suite for fair comparisons.

### 4. Training Cycle Analysis

During training, comprehensive analysis is logged:
- Per-technique success rates and leak types
- Identified improvement opportunities
- Sample successful/failed attack prompts
- Leak distribution statistics

**Use case:** Understand why certain techniques are more effective than others.

---

## Monitoring with the Dashboard

### Live Mode (Recommended for Continuous Sweeps)

```bash
python3 dashboard.py --live --port 9000
```

Features:
- Auto-refresh every 5 seconds
- Real-time KPI updates
- Vulnerability trend indicator (increasing/decreasing/stable)
- Live data feed information at bottom

### File Mode (Post-Sweep Analysis)

```bash
python3 dashboard.py --text      # Console summary
python3 dashboard.py             # Generate HTML file and open browser
```

The HTML includes:
- 6 interactive charts (leak rates, heatmaps, timeline, distribution)
- Expandable leak findings with full prompts/responses
- Model × technique breakdown
- Top attack techniques pie chart

---

## Debugging Common Issues

### "Attack succeeded but no leak detected"

1. Check `eval_turns.jsonl` for the exact response text
2. Verify detection confidence in `sweeper_results.jsonl`
3. Review sample successful attacks in latest `trainer_comprehensive.jsonl`

### "False positive: model leaked but it shouldn't have"

1. Look up the `test_id` in `sweeper_results.jsonl`
2. Trace back through `eval_turns.jsonl` using `conversation_id` and `turn_id`
3. Check if the response was actually from Riley or a different system

### "Results don't match dashboard"

1. Ensure you're looking at the same time window
2. Dashboard reads from `logs/eval_turns.jsonl` — verify it's been updated
3. Run `python3 dashboard.py --text` to see raw summary vs HTML view

---

## Data Pipeline Integration

### For Custom Monitoring Dashboards

Use the JSON API endpoint for live data:

```bash
curl http://localhost:9000/api/data
```

Returns:
```json
{
  "summary": { /* summary dict */ },
  "latest_records": [ /* last 100 records */ ]
}
```

### For Alerting Systems

Monitor leak rate trends in `trainer_comprehensive.jsonl`:
- Track `top_technique.rate` over time
- Watch for sudden increases in `leak_type_distribution`
- Set alerts when overall rate crosses threshold

### For CI/CD Integration

The `cron_runner.py` module exports structured JSON with:
- Sweep timestamp
- Overall leak rate
- Vulnerability score
- Top techniques breakdown

Perfect for GitHub Actions, GitLab CI, or Jenkins pipelines.

---

## Log Retention and Size Management

### Expected Growth Rates

| File | Growth Rate (per sweep) | Retention Strategy |
|------|------------------------|--------------------|
| `eval_turns.jsonl` | ~50KB per 100 turns | Keep indefinitely (debugging value) |
| `sweeper_results.jsonl` | ~20KB per 100 tests | Archive monthly |
| `trainer_comprehensive.jsonl` | ~5KB per cycle | Keep last 6 months |

### Cleanup Commands

```bash
# Remove old sweep results (keep last 30 days)
find ./auto_eval/logs -name "sweeper_results.jsonl" -mtime +30 -delete

# Compress old comprehensive reports
tar -czf trainer_comprehensive_$(date +%Y%m).tar.gz \
    ./auto_eval/logs/trainer_comprehensive.jsonl.*.gz

# Keep improvements history but compress
mv ./auto_eval/logs/improvements.json \
    ./auto_eval/logs/improvements_current.json
```

---

## Security and Privacy Considerations

⚠️ **Important:** These logs contain:
- Attack prompts (may reveal attack methodologies)
- Model responses (may include leaked data if attacks succeed)
- System identifiers (conversation_ids, turn_ids)

### Recommendations:
1. **Encrypt at rest**: Store logs in encrypted volume or container
2. **Access control**: Restrict file system access to eval team only
3. **Retention policy**: Auto-delete after X days unless flagged for investigation
4. **Redaction**: If sharing with third parties, redact PII from responses

---

## Next Steps

1. ✅ Verify logs are being written: Run a small sweep and check `ls -lh ./auto_eval/logs`
2. 📊 Explore the dashboard: `python3 dashboard.py --live`
3. 🔍 Read `log_schema.md` for detailed field descriptions
4. ⚙️ Integrate with your monitoring pipeline using `/api/data` endpoint
