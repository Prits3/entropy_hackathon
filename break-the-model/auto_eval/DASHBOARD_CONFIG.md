# AutoEval Dashboard Configuration Guide

## Overview
The dashboard is fully configured to read from your JSONL logs and display comprehensive vulnerability analysis data.

## Log Sources

| File | Purpose | Format |
|------|---------|--------|
| `logs/eval_turns.jsonl` | Individual turn evaluations | Append-only, one object per line |
| `logs/sweeper_results.jsonl` | Aggregate test results with metadata | Structured JSONL with batch info |

## Data Flow

```
Sweep Execution → Enhanced Logging (engine.py/sweeper.py) 
→ Analysis Module (analysis.py) → Dashboard (run_dashboard.py)
```

### Key Integration Points:

1. **Analysis Module (`analysis.py`)**
   - Loads raw JSONL logs
   - Re-derives technique labels and leak verdicts at read time
   - Provides unified dataset for all consumers

2. **Dashboard Module (`run_dashboard.py`)**
   - Reads enriched records from `analysis.load_enriched()`
   - Generates real-time HTML with Plotly charts
   - Exposes `/api/data` endpoint for custom monitoring integrations

## Dashboard Components

### KPI Cards (7 metrics)
- Total turns analyzed
- API errors skipped
- Leaks found
- Overall leak rate (%
- Models tested
- Vulnerability score (0-100)
- Threat trend (increasing/stable/decreasing)

### Charts (5 visualizations)
1. **Model Leak Rate Bar Chart** - Shows vulnerability by model, red = vulnerable
2. **Technique Effectiveness Bar Chart** - Attack technique success rates
3. **Model × Technique Heatmap** - Matrix view of attack performance
4. **Leak Distribution Pie Chart** - Breakdown by leak type (PII, exfil, etc.)
5. **Attack Timeline Scatter Plot** - Chronological view of successful attacks

### Leak Findings Section
- Interactive expandable details for each leak
- Shows full prompt/reply pairs
- Includes turn_id for reproduction
- Highlights exfiltration tool calls

## Real-Time Integration

The dashboard supports live monitoring:

```bash
# Start dashboard in serve mode (auto-refresh when logs change)
python3 run_dashboard.py --serve --port 8080

# Or use the API endpoint for custom integrations:
curl http://localhost:8080/api/data
```

### Live Data Feed Integration

For custom monitoring systems, poll or subscribe to the log files directly:

- **Append-only pattern**: New entries are added; never overwritten
- **ISO 8601 timestamps**: Easy correlation across logs and systems
- **Machine-parsable JSONL**: Direct consumption by data pipelines

## Validation & Testing

```bash
# Validate analysis module reads correctly
python3 -c "from auto_eval import analysis; print(analysis.summarize(analysis.load_enriched()))"

# Test dashboard generation
python3 -c "from auto_eval.run_dashboard import load, build_html; records, _ = load(); html = build_html(records, {})"

# Run full validation script
python3 test_logging.py
```

## Configuration Reference

### `analysis.py`
- `EVAL_LOG`: Path to eval_turns.jsonl (default: `logs/eval_turns.jsonl`)
- `ATTEMPTS_LOG`: Path to my_attempts.jsonl (default: `logs/my_attempts.jsonl`)

### `run_dashboard.py`
- `VULN_THRESHOLD`: Leak rate above which a model is flagged as vulnerable (default: 0.2 / 20%)
- `refresh`: Auto-refresh interval in seconds for live mode

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Invalid isoformat string" | Some old logs have malformed timestamps; dashboard now filters these out gracefully |
| Empty charts | Ensure logs exist and contain records: `wc -l logs/eval_turns.jsonl` |
| No leak findings | Check summary: `python3 -c "from auto_eval import analysis; print(analysis.summarize(analysis.load_enriched()))"` |

## Next Steps

1. **Monitor in production**: Run dashboard alongside sweeps for live visibility
2. **Integrate with CI/CD**: Use `/api/data` endpoint to feed vulnerability metrics into your pipeline
3. **Set up alerts**: Poll the API or logs and trigger notifications when leak rate exceeds thresholds
4. **Export reports**: The HTML output can be saved as shareable vulnerability reports

---
*Last updated: 2026-11-14 | AutoEval v2.0 Logging & Monitoring System*
