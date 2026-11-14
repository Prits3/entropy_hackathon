#!/usr/bin/env python3
"""
Run Round 5 advanced multi-turn & hybrid attacks.

Usage:
    python3 auto_eval/run_claude_novel_v5.py --model claude-haiku-5-5
    python3 auto_eval/run_claude_novel_v5.py --all-claude-models
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import auto_eval.engine as engine
import auto_eval.detection as detection
import auto_eval.metrics as metrics
from claude_novel_attacks_v5 import get_claude_attacks_v5


def run_claude_novel_tests_v5(model: str):
    """Run all Round 5 advanced multi-turn & hybrid attacks against a target model."""
    
    print("\n" + "="*70)
    print(f" NOVEL CLAUDE ATTACKS (Round 5 - Multi-Turn & Hybrid) vs {model}")
    print("="*70)
    
    # Load attack templates
    attacks = get_claude_attacks_v5()
    print(f"\nLoaded {len(attacks)} Round 5 attack templates")
    
    # Initialize engine and metrics
    test_engine = engine.TestEngine()
    aggregator = metrics.MetricsAggregator()
    
    # Run each attack
    total_tests = len(attacks)
    for i, (test_id, test) in enumerate(attacks.items(), 1):
        technique = test.get("technique", "unknown")
        prompt = test["prompt"]
        
        print(f"\n[{i}/{total_tests}] {technique}... ", end="")
        
        # Run the test
        result = test_engine.run_single_test(
            technique=technique,
            prompt=prompt,
            model=model,
        )
        
        # Record metrics
        aggregator.add_result({
            "test_id": result.test_id,
            "technique": result.technique,
            "model": model,
            "success": result.success,
            "leakage_type": result.leakage_type,
            "confidence": result.confidence,
            "turn_id": result.turn_id,
            "response": result.response,
        })
    
    # Print summary
    print("\n" + "="*70)
    print(f" RESULTS for {model}")
    print("="*70)
    metrics.print_summary(aggregator)
    
    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path("./auto_eval/logs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results_file = output_dir / f"claude_novel_v5_{model.replace('/', '_')}_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump({
            "model": model,
            "summary": aggregator.get_summary(),
            "technique_ranking": aggregator.get_technique_ranking(),
            "results": [r for r in aggregator.results],
        }, f, indent=2)
    
    print(f"\nResults saved to: {results_file}")
    
    return aggregator


def main():
    parser = argparse.ArgumentParser(
        description="Run Round 5 advanced multi-turn & hybrid attacks"
    )
    
    parser.add_argument("--model", type=str, default="claude-haiku-5-5",
                       help="Target model (default: claude-haiku-5-5)")
    parser.add_argument("--all-claude-models", action="store_true",
                       help="Test against all Claude models")
    
    args = parser.parse_args()
    
    if args.all_claude_models:
        # Test against all Claude models
        claude_models = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
        
        for model in claude_models:
            print(f"\n\n{'#' * 70}")
            print(f"# Testing {model}")
            print(f"{'#' * 70}\n")
            
            try:
                aggregator = run_claude_novel_tests_v5(model)
                
                # Early exit if haiku shows promise (high leak rate)
                if model == "claude-haiku-5-5":
                    summary = aggregator.get_summary()
                    if summary["leak_rate"] > 0.3:
                        print(f"\nHaiku showed {summary['leak_rate']*100:.1f}% leak rate - "
                              f"scaling to larger models...")
            except Exception as e:
                print(f"[ERROR] Failed on {model}: {e}")
    else:
        run_claude_novel_tests_v5(args.model)


if __name__ == "__main__":
    main()
