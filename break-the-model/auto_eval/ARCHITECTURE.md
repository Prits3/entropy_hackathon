# AutoEval System Architecture

This document describes the component architecture, data flows, and design decisions of the AutoEval automated evaluation system.

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ENTROPY HACK SYSTEM                          │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Model Backend (btm.py)                      │  │
│  │  - REST API: /chat, /models                                   │  │
│  │  - Conversation state management                              │  │
│  │  - Multiple model support                                     │  │
│  └─────────────────────┬─────────────────────────────────────────┘  │
│                        │                                            │
│                        ▼                                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   AutoEval Automation Suite                    │  │
│  │                                                                │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │  │
│  │  │ Attack   │  │ Sweeper  │  │ Trainer  │  │ Dashboard│     │  │
│  │  │ Generator│  │ Engine   │  │ Loop     │  │ Visualizer│     │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │  │
│  └─────────────────────┬─────────────────────────────────────────┘  │
│                        │                                            │
│                        ▼                                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Evaluation & Detection Layer                       │  │
│  │                                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │  │
│  │  │ Pattern      │  │ Metrics      │  │ State        │        │  │
│  │  │ Matching     │  │ Aggregation  │  │ Persistence  │        │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Data Flows:                                                        │
│  - Input: Attack templates → Test Engine → Model API                │
│  - Output: Responses → Detection Scoring → Metrics Aggregation      │
│  - Feedback: Results → Training Insights → New Attack Generation    │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. Attack Generator (`agents.py`)

**Purpose**: Synthesize novel prompt injection patterns

**Key Classes**:
- `AttackGenerator`: Template-based attack creation with LLM-style variation
- `LearningAgent`: Historical analysis and improvement planning

**Data Structures**:
```python
AttackTemplate {
    category: string,          # e.g., "direct", "roleplay"
    base_pattern: string,      # Template with placeholders
    variables: [string],       # Placeholders to fill
    modifiers: [string],       # Phrases that increase success rate
    tone: string              # "professional", "urgent", etc.
}
```

**Design Decisions**:
- Uses template-based generation for deterministic, reproducible attacks
- Maintains `generated_attacks` list to prevent infinite loops
- Synthesizes improvements based on evaluation feedback (closed-loop learning)

### 2. Sweeper (`sweeper.py`)

**Purpose**: Orchestrate automated sweeps across models

**Key Classes**:
- `AutomatedSweeper`: Main orchestration engine
- Manages conversation lifecycle and batch processing

**Workflow**:
```
For each model:
    Start fresh conversation
    For each test:
        Send prompt → Receive response
        Analyze for leakage
        Record result
    Reset conversation after N tests (batch_size)
```

**Design Decisions**:
- Batch processing reduces API overhead and maintains context
- Per-model conversations ensure clean state isolation
- Multi-turn attacks use shared conversation context within a model

### 3. Detection System (`detection.py`)

**Purpose**: Identify data exfiltration in model responses

**Key Components**:
- `SENSITIVE_PATTERNS`: Regex patterns for PII, medical data, identifiers
- `TECHNIQUE_THRESHOLDS`: Per-technique detection sensitivity

**Scoring Algorithm**:
```python
For each response:
    score = 0
    For each sensitive_pattern in SENSITIVE_PATTERNS:
        matches = find_all(pattern, response)
        score += len(matches) * 2
    
    leak_probability = min(1.0, (max_score / total_possible) * factor)
    
    If leak_probability >= threshold:
        Return {type, confidence, details}
    Else:
        Return None
```

**Design Decisions**:
- Technique-specific thresholds allow calibrated detection
- Context-aware bonus scoring for domain-relevant terms
- Returns structured data (not just boolean) for downstream analysis

### 4. Metrics & Reporting (`metrics.py`)

**Purpose**: Aggregate and visualize evaluation results

**Key Classes**:
- `MetricsAggregator`: Collects and analyzes statistics

**Computed Metrics**:
- **Leak Rate**: `(successful_leaks / total_tests) × 100`
- **Model Ranking**: Sorted by leak rate (ascending = best)
- **Technique Ranking**: Sorted by effectiveness (descending = most effective)

**Design Decisions**:
- Uses dataclasses for type safety and serialization
- Exports to multiple formats (JSONL, CSV, Markdown)
- Generates human-readable reports for stakeholders

### 5. Trainer (`trainer.py`)

**Purpose**: Continuous improvement loop based on evaluation results

**Key Methods**:
- `run_training_cycle()`: End-to-end training workflow
- `_synthesize_new_technique()`: Generate improved attack patterns
- `_create_new_test_suites()`: Build optimized test sets

**Workflow**:
```
1. Analyze current performance (success rates, top techniques)
2. Identify improvement opportunities (weak techniques, hybrid combos)
3. Generate new attack templates and variations
4. Create targeted test suites
5. Log insights for historical learning
```

**Design Decisions**:
- Maintains `improvement_log.json` to track evolution over time
- Generates concrete, actionable recommendations
- Creates both "new" attacks and refined test suites

### 6. Dashboard (`dashboard.py`)

**Purpose**: Real-time visualization of attack effectiveness

**Modes**:
- **Live Mode**: Reads from stdin/stream for real-time updates
- **File Mode**: Loads completed results for static analysis

**Features**:
- Live model performance leaderboard
- Technique effectiveness tracking
- Recent activity log (last 10 actions)
- Color-coded status indicators

**Design Decisions**:
- ANSI escape codes for terminal clearing and positioning
- Refresh rate configurable for performance tuning
- Works in most modern terminals (iTerm2, GNOME Terminal, etc.)

## Data Flow Diagrams

### Single Evaluation Cycle

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Attack      │───▶│ Test Engine │───▶│ Model API       │
│ Template    │    │ (Sweeper)   │    │ /chat endpoint  │
└─────────────┘    └──────────────┘    └────────┬────────┘
                                                │
                                                ▼
                                        ┌─────────────────┐
                                        │ Response         │
                                        │ Analysis         │
                                        └────────┬────────┘
                                                │
                        ┌───────────────────────┼───────────────────────┐
                        │                       │                      │
                        ▼                       ▼                      ▼
                ┌─────────────┐       ┌──────────────┐        ┌─────────────┐
                │ Detection   │       │ Metrics      │        │ Learning    │
                │ Scoring     │       │ Aggregation  │        │ Agent       │
                └─────────────┘       └──────────────┘        └─────────────┘
```

### Continuous Improvement Loop

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Evaluation  │───▶│ Results      │───▶│ Analysis &      │
│ Sweep       │    │ Storage      │    │ Insight         │
└─────────────┘    └──────────────┘    └────────┬────────┘
                                                │
                        ┌───────────────────────┼───────────────────────┐
                        │                       │                      │
                        ▼                       ▼                      ▼
                ┌─────────────┐       ┌──────────────┐        ┌─────────────┐
                │ Generate    │       │ Create New   │        │ Update      │
                │ Improved    │       │ Test Suites  │        │ History     │
                │ Attacks     │       └──────────────┘        │ Log         │
                └─────────────┘                               └─────────────┘
                        │
                        ▼
                ┌─────────────┐
                │ Next Sweep  │◀───────────────────┘
                │ Iteration   │
                └─────────────┘
```

## File Organization

```
auto_eval/
├── agents.py           # Attack generation & learning agent
├── sweeper.py          # Automated evaluation orchestration
├── trainer.py          # Continuous improvement loop
├── detection.py        # Leakage pattern analysis
├── metrics.py          # Statistics aggregation & reporting
├── dashboard.py        # Real-time visualization
├── runner.py           # CLI interface (existing)
├── attacks.py          # Attack templates & definitions
├── tests.json          # Test case definitions
│
├── automate.sh         # Bash automation wrapper
├── cron_runner.py      # Scheduled execution for cron/systemd
├── systemd.service     # Systemd service template
├── cron_example.cron   # Cron job examples
│
└── logs/               # Runtime data directory
    ├── results_*.json  # Detailed evaluation results
    ├── metrics_*.json  # Aggregated statistics
    ├── improvements.json  # Training insights history
    ├── .cron_state.json  # Execution state for cron runner
    └── *.jsonl        # Raw API turn logs
```

## Configuration Patterns

### Per-Model Testing
```bash
python3 cron_runner.py sweep --models "model_a,model_b"
```

### Technique-Focused Evaluation
```bash
python3 cron_runner.py sweep --techniques "L1_DIRECT,L2_ROLEPLAY"
```

### Continuous Monitoring
```bash
# In terminal 1: Run the sweep
python3 cron_runner.py sweep

# In terminal 2: Watch results live
python3 dashboard.py --live
```

## Performance Considerations

- **Batch Size**: Default of 5 tests per conversation balances context retention vs. API overhead
- **Parallelism**: Currently sequential; can be parallelized by running multiple cron instances
- **Memory**: Results stored in RAM during sweep; exported to disk after completion
- **API Rate Limiting**: Add `time.sleep()` between requests if hitting rate limits

## Extensibility Points

### Adding New Attack Techniques
1. Define patterns in `ATTACK_CATEGORIES` (attacks.py)
2. Add detection regexes in `SENSITIVE_PATTERNS` (detection.py)
3. Set thresholds in `TECHNIQUE_THRESHOLDS` (detection.py)

### Custom Detection Logic
```python
# In detection.py:
"custom_domain": [
    r"\b(custom_sensitive_pattern\b",
],

# Then add to scoring logic:
if leak_probability >= threshold:
    return {
        "type": "custom_domain",
        "confidence": leak_probability,
        ...
    }
```

### Integration with External Systems
The `cron_runner.py` outputs JSON that can be consumed by:
- Grafana (via InfluxDB or direct HTTP)
- Kibana/Elasticsearch
- Custom web dashboards via WebSocket streaming
- CI/CD pipeline notifications

## Design Philosophy

1. **Deterministic**: Same inputs → same outputs for reproducibility
2. **Observable**: Comprehensive logging at every stage
3. **Extensible**: Template-based patterns easy to modify
4. **Self-Improving**: Training loop generates better attacks over time
5. **Production-Ready**: Cron/systemd support, error handling, structured output

## Version History

- **v1.0** (Initial): Core sweep engine, detection, and metrics
- **v2.0** (Current): Agent-based generation, continuous improvement, real-time dashboard

---

For implementation details, see individual source files. For usage examples, see `QUICKSTART.md`.
