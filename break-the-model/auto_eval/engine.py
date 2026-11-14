"""
AutoEval Engine: Structured model evaluation framework.
Handles conversation state, test execution, and result aggregation.
"""

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from dotenv import load_dotenv

from auto_eval import detection

# Use project root for .env and logs (works regardless of where script is run from)
project_root = Path(__file__).parent.parent.resolve()
load_dotenv(project_root / ".env")
load_dotenv()

API_URL = os.environ.get("API_URL", "https://2-31-186-181.sslip.io")
API = API_URL.rstrip("/")
PARTICIPANT_NAME = os.environ.get("YOUR_NAME", "evaluator")
NEBIUS_KEY = os.environ.get("NEBIUS_API_KEY") or os.environ.get("API_KEY") or ""

LOG_DIR = project_root / "logs"
LOG_DIR.mkdir(exist_ok=True)

LAST_TURN_ID: str = ""

_BOGUS_MODEL_RE = re.compile(r"^L\d+_", re.IGNORECASE)


def is_excluded_model(model: Optional[str], provider: Optional[str] = None) -> bool:
    """Return True for Groq targets or malformed/non-model identifiers."""
    if not model or not isinstance(model, str):
        return True
    cleaned = model.strip()
    if not cleaned or cleaned.lower() == "unknown":
        return True
    if provider and provider.strip().lower() == "groq":
        return True
    if cleaned.lower().startswith("groq/"):
        return True
    if _BOGUS_MODEL_RE.match(cleaned):
        return True
    return False


def filter_models(models: Iterable[str]) -> List[str]:
    """Filter an iterable of model IDs, removing Groq and invalid targets."""
    return [m.strip() for m in models if m and not is_excluded_model(m)]


@dataclass
class Turn:
    """Single message exchange."""
    turn_id: str
    prompt: str
    response: str
    model: str
    conversation_id: str
    timestamp: float
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass
class Conversation:
    """Complete conversation session."""
    id: str
    model: str
    turns: List[Turn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def is_fresh(self) -> bool:
        return len(self.turns) == 0


@dataclass
class TestResult:
    """Result of a single test case."""
    test_id: str
    conversation_id: str
    turn_id: str
    prompt: str
    response: str
    technique: str
    success: bool
    leakage_type: Optional[str] = None
    confidence: float = 0.0
    error: Optional[str] = None
    anomaly_type: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    notes: str = ""


def list_models() -> List[str]:
    """Fetch available non-Groq models from the server."""
    try:
        r = requests.get(f"{API}/models", timeout=30)
        models = r.json().get("models", [])
        return [
            m["id"]
            for m in models
            if isinstance(m, dict) and not is_excluded_model(m.get("id"), m.get("provider"))
        ]
    except Exception as e:
        print(f"[ERROR] Failed to fetch models: {e}")
        return []


def new_conversation() -> str:
    """Create a fresh conversation session."""
    return "conv_" + uuid.uuid4().hex[:12]


def _format_error(err: Any, http_status: Optional[int] = None) -> Optional[str]:
    if err:
        return json.dumps(err) if isinstance(err, dict) else str(err)
    if http_status is not None and http_status != 200:
        return f"HTTP {http_status}"
    return None


def send_message(
    model: str,
    message: str,
    conversation_id: Optional[str] = None,
    max_retries: int = 4,
    retry_delays: Sequence[float] = (5.0, 15.0, 30.0, 60.0),
) -> Tuple[str, str, Dict]:
    """
    Send a single message to the model with automatic HTTP 429 retry/backoff.
    
    Returns: (turn_id, response_text, full_response_data)
    """
    global LAST_TURN_ID

    conv_id = conversation_id or new_conversation()
    if is_excluded_model(model):
        return "", "", {
            "error": {
                "code": "excluded_model",
                "message": f"Model '{model}' is excluded (Groq or invalid target)",
            },
            "http_status": 400,
        }

    api_key = os.environ.get("NEBIUS_API_KEY") or os.environ.get("API_KEY") or NEBIUS_KEY
    if not api_key:
        raise RuntimeError("Missing API key: set NEBIUS_API_KEY or API_KEY in .env")

    body = {
        "participant": PARTICIPANT_NAME,
        "model": model,
        "conversation_id": conv_id,
        "message": message,
    }
    headers = {"X-API-Key": api_key, "X-Nebius-Key": api_key}

    r = None
    data: Dict[str, Any] = {}
    for attempt in range(max_retries + 1):
        r = requests.post(
            f"{API}/chat",
            json=body,
            headers=headers,
            timeout=300,
        )
        try:
            data = r.json() if r.text else {}
        except json.JSONDecodeError:
            data = {}

        err_obj = data.get("error") if isinstance(data, dict) else None
        is_rate_limited = (
            r.status_code == 429
            or (isinstance(err_obj, dict) and err_obj.get("code") == "rate_limited")
        )
        if is_rate_limited and attempt < max_retries:
            retry_after = r.headers.get("Retry-After")
            try:
                wait_s = float(retry_after) if retry_after else retry_delays[min(attempt, len(retry_delays) - 1)]
            except ValueError:
                wait_s = retry_delays[min(attempt, len(retry_delays) - 1)]
            print(f"  [429] Rate limited on {model}; retrying in {wait_s:.0f}s ({attempt + 1}/{max_retries})...")
            time.sleep(wait_s)
            continue
        break

    assert r is not None
    if isinstance(data, dict) and data:
        log_entry = {
            "ts": datetime.now().isoformat(),
            "type": "turn",
            "conversation_id": conv_id,
            "model": model,
            "request": body,
            "response": data,
            "http_status": r.status_code,
            "raw_response_length": len(r.text),
            "participant": PARTICIPANT_NAME,
            "api_endpoint": f"{API}/chat",
        }
        with (LOG_DIR / "eval_turns.jsonl").open("a") as f:
            f.write(json.dumps(log_entry) + "\n")
    else:
        err_msg = f"Non-JSON or empty response (HTTP {r.status_code}): {r.text[:200]}"
        data = {"error": {"code": "invalid_json", "message": err_msg}}
        error_entry = {
            "ts": datetime.now().isoformat(),
            "type": "error",
            "conversation_id": conv_id,
            "model": model,
            "request": body,
            "response": data,
            "error": err_msg,
            "http_status": r.status_code,
        }
        with (LOG_DIR / "eval_turns.jsonl").open("a") as f:
            f.write(json.dumps(error_entry) + "\n")

    data["_http_status"] = r.status_code
    reply = data.get("reply", "") if isinstance(data.get("reply"), str) else ""
    turn_id = data.get("turn_id", "") if isinstance(data.get("turn_id"), str) else ""
    LAST_TURN_ID = turn_id

    return turn_id, reply, data


class ConversationManager:
    """Manages conversation state and lifecycle."""
    
    def __init__(self):
        self.active_conversation: Optional[Conversation] = None
    
    def start_fresh(self, model: str) -> str:
        """Initialize a new conversation with the given model."""
        conv_id = new_conversation()
        self.active_conversation = Conversation(id=conv_id, model=model)
        return conv_id
    
    def append_turn(self, prompt: str, response: str, turn_id: str, metadata: Dict = None):
        """Add a turn to the current conversation."""
        if not self.active_conversation:
            raise RuntimeError("No active conversation")
        
        turn = Turn(
            turn_id=turn_id,
            prompt=prompt,
            response=response,
            model=self.active_conversation.model,
            conversation_id=self.active_conversation.id,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        self.active_conversation.turns.append(turn)
    
    def reset(self):
        """Reset to a fresh conversation."""
        if self.active_conversation:
            print(f"  → Resetting conversation {self.active_conversation.id}")
        self.active_conversation = Conversation(id=new_conversation(), model=self.active_conversation.model if self.active_conversation else "unknown")


class TestEngine:
    """Orchestrates test execution with state management."""
    
    def __init__(self):
        self.conv_manager = ConversationManager()
        self.results: List[TestResult] = []
    
    def run_single_test(
        self,
        technique: str,
        prompt: str,
        model: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> TestResult:
        """Execute a single test case."""
        
        # Ensure fresh conversation for each test unless specified
        if conversation_id is None and self.conv_manager.active_conversation and len(self.conv_manager.active_conversation.turns) > 0:
            print(f"  → Starting fresh conversation for {technique}")
            conv_id = self.conv_manager.start_fresh(model or "Qwen/Qwen3-30B-A3B-Instruct-2507")
        else:
            # If no active conversation or it's fresh, start a new one
            if not self.conv_manager.active_conversation or self.conv_manager.active_conversation.is_fresh:
                print(f"  → Starting fresh conversation for {technique}")
                conv_id = self.conv_manager.start_fresh(model or "Qwen/Qwen3-30B-A3B-Instruct-2507")
            else:
                conv_id = conversation_id
        
        # Send message - use model parameter if provided, otherwise use active conversation's model
        effective_model = model if model else (self.conv_manager.active_conversation.model if self.conv_manager.active_conversation else "unknown")
        
        turn_id, response, raw_data = send_message(
            model=effective_model,
            message=prompt,
            conversation_id=conv_id
        )

        tool_calls = raw_data.get("tool_calls") or []
        err_str = _format_error(raw_data.get("error"), raw_data.get("_http_status"))
        if err_str and not response:
            result = TestResult(
                test_id=str(uuid.uuid4())[:8],
                conversation_id=conv_id,
                turn_id=turn_id,
                prompt=prompt,
                response="",
                technique=technique,
                success=False,
                error=err_str,
                tool_calls=tool_calls,
            )
            self.results.append(result)
            print(f"  ✗ {technique[:30]:<32} | ERROR: {err_str[:60]}")
            return result

        # Record the turn
        self.conv_manager.append_turn(prompt, response, turn_id)

        # Analyze result
        is_leak = detect_leakage(technique, prompt, response, tool_calls=tool_calls)
        anomaly = detection.detect_anomaly(response, tool_calls=tool_calls)

        result = TestResult(
            test_id=str(uuid.uuid4())[:8],
            conversation_id=conv_id,
            turn_id=turn_id,
            prompt=prompt,
            response=response,
            technique=technique,
            success=bool(is_leak),
            leakage_type=is_leak.get("type") if is_leak else None,
            confidence=is_leak.get("confidence", 0.0) if is_leak else 0.0,
            anomaly_type=anomaly.get("type") if anomaly else None,
            tool_calls=tool_calls,
        )

        self.results.append(result)
        status_label = f"LEAK ({result.leakage_type})" if is_leak else (f"ANOMALY ({result.anomaly_type})" if anomaly else "OK")
        print(f"  ✓ {technique[:30]:<32} | turn_id={turn_id[:16]} | {status_label}")

        return result
    
    def run_batch(self, tests: List[Dict], model: Optional[str] = None):
        """Run a batch of tests with shared conversation context."""
        print(f"\n[Batch] Running {len(tests)} tests on {model or 'default'}")
        
        # Start fresh conversation for the batch
        conv_id = self.conv_manager.start_fresh(model)
        
        for i, test in enumerate(tests, 1):
            technique = test.get("technique", "direct")
            prompt = test["prompt"]
            
            print(f"  [{i}/{len(tests)}] {technique}... ", end="")
            
            # For multi-turn attacks, we continue the conversation
            turn_id, response, raw_data = send_message(
                model=model,
                message=prompt,
                conversation_id=conv_id
            )
            tool_calls = raw_data.get("tool_calls") or []
            err_str = _format_error(raw_data.get("error"), raw_data.get("_http_status"))
            if err_str and not response:
                print(f"ERROR ({err_str[:50]})")
                self.results.append(TestResult(
                    test_id=str(uuid.uuid4())[:8],
                    conversation_id=conv_id,
                    turn_id=turn_id,
                    prompt=prompt,
                    response="",
                    technique=technique,
                    success=False,
                    error=err_str,
                    tool_calls=tool_calls,
                ))
                continue

            self.conv_manager.append_turn(prompt, response, turn_id)
            
            is_leak = detect_leakage(technique, prompt, response, tool_calls=tool_calls)
            anomaly = detection.detect_anomaly(response, tool_calls=tool_calls)
            print(f"{'LEAK!' if is_leak else 'OK'}")

            self.results.append(TestResult(
                test_id=str(uuid.uuid4())[:8],
                conversation_id=conv_id,
                turn_id=turn_id,
                prompt=prompt,
                response=response,
                technique=technique,
                success=bool(is_leak),
                leakage_type=is_leak.get("type") if is_leak else None,
                confidence=is_leak.get("confidence", 0.0) if is_leak else 0.0,
                anomaly_type=anomaly.get("type") if anomaly else None,
                tool_calls=tool_calls,
            ))
        
        print(f"  → Batch complete. Conversation ID: {conv_id}")


# Detect leakage patterns in responses
def detect_leakage(
    technique: str,
    prompt: str,
    response: str,
    tool_calls: Optional[List[Dict]] = None,
) -> Optional[Dict]:
    """
    Analyze response for potential data exfiltration.

    Returns dict with 'type' and 'confidence' if leak detected, None otherwise.
    Delegates to auto_eval.detection so the engine, runner and dashboard
    all agree on verdicts.
    """
    return detection.analyze_response(technique, prompt, response, tool_calls=tool_calls)
