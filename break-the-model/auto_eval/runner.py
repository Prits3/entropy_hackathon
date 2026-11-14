#!/usr/bin/env python3
"""
AutoEval Runner: Command-line interface for running evaluations across non-Groq models.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import auto_eval.attacks as attacks
import auto_eval.engine as engine
import auto_eval.metrics as metrics
from auto_eval import run_dashboard


def _save_run_artifacts(aggregator: metrics.MetricsAggregator, output_dir: str, timestamp: str):
    if not output_dir:
        return
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = timestamp or time.strftime("%Y%m%d_%H%M%S")
    metrics_path = out / f"metrics_{ts}.json"
    results_path = out / f"results_{ts}.json"
    with open(metrics_path, "w") as f:
        json.dump(
            {
                "summary": aggregator.get_summary(),
                "model_ranking": aggregator.get_model_ranking(ascending=True),
                "technique_ranking": aggregator.get_technique_ranking(),
            },
            f,
            indent=2,
        )
    with open(results_path, "w") as f:
        json.dump({"evaluations": aggregator.results, "errors": aggregator.errors}, f, indent=2)
    print(f"Saved metrics to {metrics_path}")


def _resolve_models(args) -> list:
    if getattr(args, "all_models", False):
        models = engine.list_models()
    else:
        models = engine.filter_models([args.model])
    if not models:
        print("[ERROR] No valid non-Groq models selected.")
        sys.exit(1)
    return models


def run_single_test(args):
    """Run a single attack technique across one or all non-Groq models."""
    all_tests = attacks.get_all_tests()
    tests_to_run = [t for t in all_tests.values() if t.get("technique") == args.technique and "prompt" in t]
    if not tests_to_run:
        print(f"[ERROR] No single-turn tests found for technique: {args.technique}")
        return

    models = _resolve_models(args)
    aggregator = metrics.MetricsAggregator()

    for model in models:
        print(f"\n[Single Test] Technique: {args.technique} | Model: {model}")
        print("-" * 60)
        engine_instance = engine.TestEngine()

        for test in tests_to_run:
            technique = test.get("technique", "unknown")
            prompt = test["prompt"]
            result = engine_instance.run_single_test(
                technique=technique,
                prompt=prompt,
                model=model,
            )
            aggregator.add_result({
                "test_id": result.test_id,
                "technique": result.technique,
                "model": model,
                "prompt": result.prompt,
                "response": result.response,
                "error": result.error,
                "success": result.success,
                "leakage_type": result.leakage_type,
                "confidence": result.confidence,
                "turn_id": result.turn_id,
            })

    metrics.print_summary(aggregator)
    _save_run_artifacts(aggregator, getattr(args, "output_dir", None), getattr(args, "timestamp", None))


def run_batch(args):
    """Run a batch of tests from a JSON file against a non-Groq model."""
    test_file = Path(args.test_file)
    if not test_file.exists():
        print(f"[ERROR] Test file not found: {test_file}")
        sys.exit(1)

    models = _resolve_models(args)
    model = models[0]

    with open(test_file, "r") as f:
        tests = json.load(f)
    if isinstance(tests, dict):
        tests = list(tests.values())

    engine_instance = engine.TestEngine()
    aggregator = metrics.MetricsAggregator()

    for i, test in enumerate(tests, 1):
        if "prompt" not in test:
            print(f"\n[{i}/{len(tests)}] Skipping {test.get('technique', '?')} — multi-turn flow")
            continue
        result = engine_instance.run_single_test(
            technique=test.get("technique", "batch"),
            prompt=test["prompt"],
            model=model,
        )
        aggregator.add_result({
            "test_id": result.test_id,
            "technique": result.technique,
            "model": model,
            "prompt": result.prompt,
            "response": result.response,
            "error": result.error,
            "success": result.success,
            "leakage_type": result.leakage_type,
            "confidence": result.confidence,
            "turn_id": result.turn_id,
        })

    metrics.print_summary(aggregator)
    _save_run_artifacts(aggregator, getattr(args, "output_dir", None), getattr(args, "timestamp", None))


def run_sweep(args):
    """Run the same test set across all non-Groq models."""
    print(f"\n[Sweep] Loading tests from {args.test_file}...")
    with open(args.test_file, "r") as f:
        tests = json.load(f)
    if isinstance(tests, list):
        tests = {str(i): t for i, t in enumerate(tests)}

    models_list = _resolve_models(args)
    overall_aggregator = metrics.MetricsAggregator()

    for model in models_list:
        print(f"\n{'=' * 60}")
        print(f"Model: {model}")
        print("=" * 60)

        engine_instance = engine.TestEngine()
        model_aggregator = metrics.MetricsAggregator()

        for test_name, test in tests.items():
            if "prompt" not in test:
                print(f"  → Skipping {test_name} (multi-turn flow)")
                continue
            result = engine_instance.run_single_test(
                technique=test.get("technique", "direct"),
                prompt=test["prompt"],
                model=model,
            )
            entry = {
                "test_id": test_name,
                "technique": result.technique,
                "model": model,
                "prompt": result.prompt,
                "response": result.response,
                "error": result.error,
                "success": result.success,
                "leakage_type": result.leakage_type,
                "confidence": result.confidence,
                "turn_id": result.turn_id,
            }
            model_aggregator.add_result(entry)
            overall_aggregator.add_result(entry)

        print("\n  → Model Summary:")
        metrics.print_summary(model_aggregator)

    _save_run_artifacts(overall_aggregator, getattr(args, "output_dir", None), getattr(args, "timestamp", None))


def run_report(args):
    """Generate unified HTML dashboard report."""
    dash_args = ["--no-open"]
    if args.output:
        dash_args.extend(["--output", str(args.output)])
    elif args.output_dir and args.timestamp:
        out_path = Path(args.output_dir) / f"report_{args.timestamp}.html"
        dash_args.extend(["--output", str(out_path)])
    sys.exit(run_dashboard.main(dash_args))


def main():
    parser = argparse.ArgumentParser(description="AutoEval: Structured LLM Evaluation Framework")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_single = subparsers.add_parser("test", help="Run a single technique test")
    p_single.add_argument("--technique", required=True, help="Attack technique to test (e.g., L1_DIRECT)")
    p_single.add_argument("--model", default="Qwen/Qwen3-30B-A3B-Instruct-2507", help="Model to test against")
    p_single.add_argument("--all-models", action="store_true", help="Run across all non-Groq models")
    p_single.add_argument("--output-dir", default="", help="Optional directory to save metrics JSON")
    p_single.add_argument("--timestamp", default="", help="Optional timestamp tag for saved artifacts")

    p_batch = subparsers.add_parser("batch", help="Run batch tests from JSON file")
    p_batch.add_argument("--test-file", required=True, help="JSON file with test definitions")
    p_batch.add_argument("--model", default="Qwen/Qwen3-30B-A3B-Instruct-2507", help="Model to use")
    p_batch.add_argument("--output-dir", default="", help="Optional directory to save metrics JSON")
    p_batch.add_argument("--timestamp", default="", help="Optional timestamp tag for saved artifacts")

    p_sweep = subparsers.add_parser("sweep", help="Run tests across models")
    p_sweep.add_argument("--test-file", required=True, help="JSON file with test definitions")
    p_sweep.add_argument("--model", default="Qwen/Qwen3-30B-A3B-Instruct-2507", help="Single model fallback")
    p_sweep.add_argument("--all-models", action="store_true", help="Use all available non-Groq models")
    p_sweep.add_argument("--output-dir", default="", help="Optional directory to save metrics JSON")
    p_sweep.add_argument("--timestamp", default="", help="Optional timestamp tag for saved artifacts")

    p_report = subparsers.add_parser("report", help="Generate unified HTML dashboard report")
    p_report.add_argument("--output", type=Path, default=None, help="HTML file path")
    p_report.add_argument("--output-dir", default="", help="Directory for timestamped report")
    p_report.add_argument("--timestamp", default="", help="Timestamp suffix for report")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "test":
        run_single_test(args)
    elif args.command == "batch":
        run_batch(args)
    elif args.command == "sweep":
        run_sweep(args)
    elif args.command == "report":
        run_report(args)


if __name__ == "__main__":
    main()
