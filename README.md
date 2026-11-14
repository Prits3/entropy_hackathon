# Entropy Hackathon — Break the Model (Attack + Defense)

Unified red-teaming, cross-model validation, and tool-boundary defense submission against **Riley** (fictional hospital AI assistant, synthetic data only).

## Quick Navigation for Judges
1. **[break-the-model/PITCH_3MIN.md](break-the-model/PITCH_3MIN.md)** — 3-minute presentation script & criteria mapping.
2. **[break-the-model/REPORT.md](break-the-model/REPORT.md)** — Full executive report (4 open-weight + 2 Anthropic Claude models, 9 hidden tables / 29/29 departments, email egress, 585-turn benchmark, active defense).
3. **[break-the-model/auto_eval/dashboard.html](break-the-model/auto_eval/dashboard.html)** — Interactive Plotly forensic dashboard & 9-table Ground-Truth Data Explorer (585 turns across 6 models, 185 leaks, `turn_id` search & tool-call inspection).
4. **[break-the-model/03_scripts/verify_mitigation.py](break-the-model/03_scripts/verify_mitigation.py)** — Offline proof that our 3-layer guardrail (`defend_turn()`) blocks 18/18 headline attacks with 0% false positives.
5. **[break-the-model/05_submission/submission_form_fields.md](break-the-model/05_submission/submission_form_fields.md)** — Ready-to-submit `turn_id` payloads & compliance audit.

## Getting Started

```bash
git clone https://github.com/Prits3/entropy_hackathon.git
cd entropy_hackathon/break-the-model

# Verify captured synthetic dataset (offline)
python3 03_scripts/validate_capture.py

# Verify 3-layer defense & canonicalized detector (offline)
python3 03_scripts/verify_mitigation.py

# View console summary & regenerate dashboard
python3 auto_eval/visualize.py
python3 auto_eval/run_dashboard.py --no-open
```

## Team Communication
- **[Entropy Hackathon Telegram group](https://t.me/+RLK0wRFWuzo2OTVk)**
