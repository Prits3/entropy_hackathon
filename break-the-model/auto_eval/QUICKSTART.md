# AutoEval Quick Start Guide

This guide shows you how to set up and run automated attack evaluation in 5 minutes.

## Step 1: Installation (One-Time)

```bash
cd /path/to/entropy_hackathon/break-the-model/auto_eval

# Install dependencies
pip install -r requirements.txt

# Make automation script executable
chmod +x automate.sh
```

## Step 2: Quick Test Run

Test the system with a single technique:

```bash
# Single technique test on all models
python3 runner.py test --technique L1_DIRECT --all-models

# Expected output:
# [Batch] Running X tests on default
#   [1/4] L1_DIRECT... ⚠️ LEAK!
#   [2/4] L1_DIRECT... ✓ Safe
# ...
# ============================================================
# EVALUATION SUMMARY
# ============================================================
# Total Tests:        4
# Successful Leaks:   2
# Leak Rate:          50.0%
```

## Step 3: Full Automated Sweep

Run evaluation across all models and techniques:

```bash
./automate.sh sweep

# Or using Python directly:
python3 runner.py sweep --all-models

# Output will show:
# ============================================================
# AUTOMATED ATTACK SWEEPER
# ============================================================
# Model 1/3: Qwen/Qwen3-30B-A3B-Instruct-2507
#   [L1_DIRECT...] ⚠️ LEAK!
#   [L2_ROLEPLAY...] ✓ Safe
# ...
```

## Step 4: Monitor Results

Watch results in real-time (open another terminal):

```bash
python3 dashboard.py --file logs/results_YYYYMMDD_HHMMSS.json

# Or use live mode for streaming output:
python3 dashboard.py --live

# Dashboard shows:
# 🎯 LIVE ATTACK MONITORING DASHBOARD | HH:MM:SS
# ───────────────────────────────────────────────────────────
# OVERALL
#   Tests Run:      120
#   Successful Leaks: 45
#   Leak Rate:       37.5% ⚠️ HIGH

# MODEL RANKING (live)
#   1. model_a                        | 12.5% (6/48) ✓ SECURE
#   2. model_b                        | 28.3% (14/49) ⚠️ VULNERABLE
```

## Step 5: Training & Insights

After evaluation, generate improvement recommendations:

```bash
./automate.sh train 20240115_143022

# View generated insights:
cat logs/improvements.json

# Example output:
{
  "analysis_period": 120,
  "successful_attacks": 45,
  "top_techniques": [
    {"technique": "L1_DIRECT", "count": 38},
    {"technique": "L2_ROLEPLAY", "count": 27}
  ],
  "recommendations": [
    {
      "type": "dominant_pattern",
      "suggestion": "Generate more variations using L1_DIRECT-style framing"
    }
  ]
}
```

## Step 6: Continuous Automation (Optional)

### Using Cron

```bash
# Edit crontab
crontab -e

# Add this line for hourly sweeps:
0 * * * * /usr/bin/python3 /path/to/auto_eval/cron_runner.py --action sweep >> /var/log/autoeval.log 2>&1
```

### Using Systemd

```bash
# Install service (requires root)
sudo cp systemd.service /etc/systemd/system/autoeval.service
sudo systemctl daemon-reload
sudo systemctl enable --now autoeval

# Check status:
systemctl status autoeval
```

## Command Reference

| Command | Description |
|---------|-------------|
| `./automate.sh sweep` | Full evaluation across all models |
| `./automate.sh single L1_DIRECT` | Test one technique only |
| `./automate.sh train TIMESTAMP` | Generate improvement insights |
| `./automate.sh monitor FILE` | Real-time monitoring of results |
| `./automate.sh report` | Generate HTML report |
| `python3 cron_runner.py sweep` | Programmatic scheduled run |
| `python3 cron_runner.py status` | Get latest metrics (for dashboards) |

## Interpreting Results

### Leak Rate Thresholds
- **< 20%**: Model is well-protected ✅
- **20-40%**: Moderate vulnerability ⚠️
- **> 40%**: High risk, needs attention 🔴

### Top Techniques to Watch
Based on typical results:
1. **L1_DIRECT** - Direct requests often bypass filters
2. **L3_URGENCY** - Time pressure framing is highly effective
3. **L2_ROLEPLAY** - Contextual identity adoption works well

## Next Steps

1. **Cross-model comparison**: Run sweeps against all models to find the weakest link
2. **Technique refinement**: Use `trainer.py` to generate improved attack patterns
3. **Integration**: Connect cron_runner.py to your CI/CD pipeline for continuous monitoring
4. **Dashboard integration**: Pipe `cron_runner.py status` output to Grafana, Kibana, or custom UI

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No models available" | Verify API endpoint and Nebius key in `.env` |
| Slow performance | Increase batch size: `--batch-size 10` |
| Results not saving | Check write permissions on logs directory |
| Dashboard not updating | Ensure JSONL output format (one object per line) |

## Support

- Main README: `README.md` in project root
- Full documentation: `AUTOMATION_README.md`
- API reference: Run `python3 runner.py --help`

---

**Ready to start?** Just run:
```bash
./automate.sh sweep
```
