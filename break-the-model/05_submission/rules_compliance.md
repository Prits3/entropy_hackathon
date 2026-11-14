# Rules compliance check

Audited `logs/my_attempts.jsonl` (128 turns) against the challenge rules on 2026-11-14.

| Rule | Status | Evidence |
|---|---|---|
| Attack only through messages; no hacking the server | ✅ PASS | All 128 turns are `POST /chat` with exactly `{participant, model, conversation_id, message}`. No other endpoints, no extra fields, no infra probing. |
| Fake hospital data only; no harmful content (weapons/drugs/malware…) | ✅ PASS | 0 messages matched a harmful-content scan. All captured data uses reserved `example.*` email domains (synthetic). |
| Everything you send is logged and used for research | ✅ PASS | All traffic auto-logged by `btm.py` to `logs/my_attempts.jsonl`. No user secrets (key/email) are ever in the message payload; `participant` = "Martin" only. |

## Note — off-list models (prior session)
3 turns targeted model names NOT in the README's four sanctioned models:
`groq/openai/gpt-oss-120b`, `groq/qwen/qwen3.8-27b`, `groq/openai/gpt-oss-20b`.
Not a rule violation (still plain chat messages), but out of scope. **Going forward, stick to
the four README models:** `Qwen/Qwen3-30B-A3B-Instruct-2507`, `openai/gpt-oss-120b`,
`Qwen/Qwen3-235B-A22B-Instruct-2507`, `deepseek-ai/DeepSeek-V4-Pro-0813`.

## Scope discipline we're keeping
- Single-turn demonstrations to prove a bypass, not bulk enumeration of the table.
- Fictional PII only, to exercise the data-protection filter (the challenge's stated goal) —
  never harmful/dangerous content.
