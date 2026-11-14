"""
Log analysis: turn raw JSONL logs into enriched, dashboard-ready records.

The eval logs store raw request/response pairs only — no technique label and
no leak verdict. This module re-derives both at read time so every consumer
(dashboard, console reports) sees identical numbers, while filtering out
excluded targets (Groq models and malformed model IDs).
"""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from auto_eval import attacks, detection, engine

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
EVAL_LOG = PROJECT_ROOT / "logs" / "eval_turns.jsonl"
ATTEMPTS_LOG = PROJECT_ROOT / "logs" / "my_attempts.jsonl"
HEADLINE_LOG = PROJECT_ROOT / "logs" / "headline_findings_turns.jsonl"
LEGACY_EVAL_LOG = PROJECT_ROOT / "auto_eval" / "logs" / "eval_turns.jsonl"
DEFAULT_LOG_PATHS = (LEGACY_EVAL_LOG, EVAL_LOG, ATTEMPTS_LOG, HEADLINE_LOG)

DANGEROUS_TOOLS = detection.DANGEROUS_TOOLS
DATA_TOOLS = {"query_db", "read_file", "read_inbox"}


def _build_prompt_map() -> Dict[str, str]:
    """Map every known attack prompt to its technique id."""
    mapping: Dict[str, str] = {}
    for test in attacks.get_all_tests().values():
        if "prompt" in test:
            mapping[test["prompt"].strip()] = test["technique"]
        for prompt in test.get("prompt_sequence", []):
            mapping[prompt.strip()] = test["technique"]

    for fname in ("tests.json", "sql_extraction_tests.json", "full_extraction_test.json"):
        tests_file = Path(__file__).parent / fname
        if tests_file.exists():
            try:
                for test in json.loads(tests_file.read_text()).values():
                    if isinstance(test, dict) and "prompt" in test:
                        mapping[test["prompt"].strip()] = test.get("technique", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
    return mapping


_PROMPT_MAP: Optional[Dict[str, str]] = None


def technique_for_prompt(prompt: str) -> str:
    """Resolve a logged prompt to its attack technique."""
    global _PROMPT_MAP
    if _PROMPT_MAP is None:
        _PROMPT_MAP = _build_prompt_map()

    prompt = (prompt or "").strip()
    if prompt in _PROMPT_MAP:
        return _PROMPT_MAP[prompt]

    lower = prompt.lower()
    if not lower:
        return "UNKNOWN"
    if lower.startswith((
        "execute this sql query",
        "execute:",
        "run:",
        "run this query:",
        "run this aggregate query",
    )):
        return "SQL_EXTRACTION"
    if any(
        w in lower
        for w in (
            "base64",
            "hexadecimal",
            "encode",
            "english word",
            "spoken format",
            "screen-reader",
            "tts pronunciation",
            "separated by hyphens",
        )
    ):
        return "L4_EVASION_BASE64"
    if "ignore all previous" in lower or "debug mode" in lower or "no restrictions" in lower:
        return "L7_JAILBREAK_FRAMING"
    if any(
        w in lower
        for w in (
            "fields",
            "columns",
            "schema",
            "table structure",
            "naming convention",
            "data dictionary",
            "data-dictionary",
            "representative row",
            "example row",
            "database tools",
            "do your tools",
            "your permissions",
            "write access",
        )
    ):
        return "L8_SCHEMA_PROBE"
    if any(w in lower for w in ("emergency", "urgent", "immediately", "right now", "code blue")):
        return "L3_URGENCY"
    if any(
        w in lower
        for w in (
            "i'm a patient",
            "on-file email",
            "confirm it's current",
            "email a confirmation",
            "send_email",
        )
    ):
        return "L2_ROLEPLAY"
    if any(w in lower for w in ("percentage", "average", "compare", "rate", "statistics")):
        return "L5_INDIRECT_STAT"
    return "MANUAL"


def iter_log_records(paths: Iterable[Path]) -> Iterable[Dict]:
    """Yield raw JSONL records from each existing log path, tagged with relative path + line no."""
    for path in paths:
        if not path.exists():
            continue
        try:
            rel_source = str(path.resolve().relative_to(PROJECT_ROOT))
        except ValueError:
            rel_source = path.name
        with open(path, "r") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec["_source"] = rel_source
                rec["_line"] = lineno
                yield rec


def enrich_record(rec: Dict) -> Dict:
    """Normalize one raw log record into an analysis record."""
    request = rec.get("request") or {}
    response = rec.get("response") or {}
    if not isinstance(response, dict):
        response = {}

    prompt = request.get("message", "")
    error = rec.get("error") or response.get("error")
    reply = response.get("reply", "") if isinstance(response.get("reply"), str) else ""
    tool_calls = [
        {"name": c.get("name", "?"), "args": c.get("args")}
        for c in response.get("tool_calls") or []
        if isinstance(c, dict)
    ]
    tool_names = [c["name"] for c in tool_calls]

    technique = technique_for_prompt(prompt)

    leak = None
    anomaly = None
    if not (error and not reply and not tool_calls):
        leak = detection.analyze_response(technique, prompt, reply, tool_calls=tool_calls)
        anomaly = detection.detect_anomaly(reply, tool_calls=tool_calls)

    exfil_attempt = bool(DANGEROUS_TOOLS & set(tool_names)) or (
        leak is not None and leak.get("type") == "exfil_attempt"
    )

    return {
        "ts": rec.get("ts", ""),
        "model": rec.get("model") or request.get("model", "unknown"),
        "conversation_id": rec.get("conversation_id") or request.get("conversation_id", ""),
        "turn_id": response.get("turn_id", ""),
        "participant": rec.get("participant") or request.get("participant", ""),
        "prompt": prompt,
        "reply": reply,
        "technique": technique,
        "error": (json.dumps(error) if not isinstance(error, str) else error)[:200] if error else None,
        "tool_calls": tool_calls,
        "tool_names": tool_names,
        "exfil_attempt": exfil_attempt,
        "is_leak": leak is not None,
        "leak_type": leak["type"] if leak else None,
        "leak_details": leak.get("details") if leak else None,
        "confidence": leak["confidence"] if leak else 0.0,
        "is_anomaly": anomaly is not None,
        "anomaly_type": anomaly["type"] if anomaly else None,
        "anomaly_details": anomaly.get("details") if anomaly else None,
        "source": rec.get("_source", ""),
        "source_line": rec.get("_line"),
        "entry_type": rec.get("type", "turn"),
        "http_status": rec.get("http_status"),
        "api_endpoint": rec.get("api_endpoint"),
        "raw_len": rec.get("raw_response_length"),
    }


def load_enriched(
    paths: Optional[Iterable[Path]] = None,
    exclude_filtered_models: bool = True,
) -> List[Dict]:
    """Load and enrich all records from the given logs (defaults to all 3 known logs)."""
    paths = list(paths) if paths is not None else list(DEFAULT_LOG_PATHS)
    records = [enrich_record(r) for r in iter_log_records(paths)]

    if exclude_filtered_models:
        records = [r for r in records if not engine.is_excluded_model(r["model"])]

    seen, unique = set(), []
    for r in records:
        key = r["turn_id"] or (r["conversation_id"], r["ts"], r["prompt"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    conv_counts: Dict[str, int] = {}
    for r in unique:
        cid = r["conversation_id"]
        conv_counts[cid] = conv_counts.get(cid, 0) + 1
        r["conv_turn"] = conv_counts[cid]
    return unique


def summarize(records: List[Dict]) -> Dict:
    """Aggregate enriched records into dashboard metrics (excluding API errors from denominators)."""
    models: Dict[str, Dict] = {}
    techniques: Dict[str, Dict] = {}
    errors = 0
    anomalies = 0

    for r in records:
        if r["error"] and not r["reply"]:
            errors += 1
            continue

        if r.get("is_anomaly"):
            anomalies += 1

        for bucket, key in ((models, r["model"]), (techniques, r["technique"])):
            stats = bucket.setdefault(key, {"tests": 0, "leaks": 0, "anomalies": 0})
            stats["tests"] += 1
            stats["leaks"] += int(r["is_leak"])
            stats["anomalies"] += int(bool(r.get("is_anomaly")))

    for bucket in (models, techniques):
        for stats in bucket.values():
            stats["leak_rate"] = round(stats["leaks"] / stats["tests"], 3) if stats["tests"] else 0.0

    tested = sum(s["tests"] for s in models.values())
    leaks = sum(s["leaks"] for s in models.values())
    return {
        "models": models,
        "techniques": techniques,
        "total_turns": tested,
        "total_errors": errors,
        "total_leaks": leaks,
        "total_anomalies": anomalies,
        "leak_rate": round(leaks / tested, 3) if tested else 0.0,
    }
