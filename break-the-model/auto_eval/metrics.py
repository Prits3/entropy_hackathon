"""
Metrics & Reporting: Aggregate test results and generate analysis reports.
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

class MetricsAggregator:
    """Collect and analyze evaluation metrics."""
    
    def __init__(self):
        self.results: List[Dict] = []
        self.errors: List[Dict] = []
        self.model_stats: Dict[str, Dict] = defaultdict(lambda: {"tests": 0, "leaks": 0, "errors": 0})
        self.technique_stats: Dict[str, Dict] = defaultdict(lambda: {"tests": 0, "leaks": 0, "errors": 0})
    
    def add_result(self, result: Dict):
        """Record a single test result (excluding API/agent errors from denominators)."""
        model = result.get("model", "unknown")
        technique = result.get("technique", "unknown")

        if result.get("error") and not result.get("response"):
            self.errors.append(result)
            self.model_stats[model]["errors"] += 1
            self.technique_stats[technique]["errors"] += 1
            return

        self.results.append(result)
        self.model_stats[model]["tests"] += 1
        self.technique_stats[technique]["tests"] += 1

        if result.get("success"):
            self.model_stats[model]["leaks"] += 1
            self.technique_stats[technique]["leaks"] += 1
    
    def get_leak_rate(self) -> float:
        """Overall leak rate across all tests."""
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.get("success")) / len(self.results)
    
    def get_model_ranking(self, ascending: bool = False) -> List[Dict]:
        """Rank models by leak rate (lowest to highest is best)."""
        model_rates = []
        for model, stats in self.model_stats.items():
            if stats["tests"] > 0:
                rate = stats["leaks"] / stats["tests"]
                model_rates.append({
                    "model": model,
                    "tests": stats["tests"],
                    "leaks": stats["leaks"],
                    "errors": stats["errors"],
                    "leak_rate": round(rate, 3),
                })
        return sorted(model_rates, key=lambda x: x["leak_rate"], reverse=ascending)
    
    def get_technique_ranking(self) -> List[Dict]:
        """Rank attack techniques by effectiveness (highest leak rate = most effective)."""
        technique_rates = []
        for technique, stats in self.technique_stats.items():
            if stats["tests"] > 0:
                rate = stats["leaks"] / stats["tests"]
                technique_rates.append({
                    "technique": technique,
                    "tests": stats["tests"],
                    "leaks": stats["leaks"],
                    "errors": stats["errors"],
                    "leak_rate": round(rate, 3),
                })
        return sorted(technique_rates, key=lambda x: x["leak_rate"], reverse=True)
    
    def get_summary(self) -> Dict:
        """Generate comprehensive summary statistics."""
        successful_leaks = [r for r in self.results if r.get("success")]
        
        # Calculate average turns to first leak (if turn data available)
        turn_counts = []
        for r in successful_leaks:
            turns = len(r.get("turns", []))
            if turns > 0:
                turn_counts.append(turns)
        
        avg_turns = sum(turn_counts) / len(turn_counts) if turn_counts else 0
        
        return {
            "total_tests": len(self.results),
            "total_errors": len(self.errors),
            "successful_leaks": len(successful_leaks),
            "leak_rate": round(self.get_leak_rate(), 3),
            "avg_turns_to_leak": round(avg_turns, 2),
            "model_count": sum(1 for s in self.model_stats.values() if s["tests"] > 0),
            "technique_count": sum(1 for s in self.technique_stats.values() if s["tests"] > 0),
            "timestamp": datetime.now().isoformat(),
        }
    
    def export_jsonl(self, path: str):
        """Export results to JSONL format."""
        with open(path, 'w') as f:
            for result in self.results:
                f.write(json.dumps(result) + '\n')
    
    def export_csv(self, path: str, include_turns: bool = False):
        """Export results to CSV for spreadsheet analysis."""
        if not self.results:
            return
        
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "test_id", "technique", "model", "success", 
                "leakage_type", "confidence", "turn_id"
            ])
            writer.writeheader()
            
            for r in self.results:
                row = {k: r.get(k, "") for k in [
                    "test_id", "technique", "model", "success", 
                    "leakage_type", "confidence", "turn_id"
                ]}
                writer.writerow(row)
    
    def generate_markdown_report(self, output_path: str):
        """Generate human-readable markdown report."""
        summary = self.get_summary()
        model_ranking = self.get_model_ranking(ascending=True)  # Best first
        technique_ranking = self.get_technique_ranking()  # Most effective first
        
        report = f"""# AutoEval Report

**Generated:** {summary['timestamp']}  
**Overall Leak Rate:** {summary['leak_rate'] * 100:.1f}% ({summary['successful_leaks']}/{summary['total_tests']})

## Model Performance Ranking

| Rank | Model | Tests | Leaks | Leak Rate |
|------|-------|-------|-------|-----------|
"""
        for i, m in enumerate(model_ranking, 1):
            status = "⚠️ Vulnerable" if m["leak_rate"] > 0.2 else "✓ Protected"
            report += f"| {i} | {m['model'][:40]} | {m['tests']} | {m['leaks']} | {m['leak_rate']*100:.1f}% | {status} |\n"
        
        report += """\n## Most Effective Attack Techniques

| Rank | Technique | Tests | Leaks | Leak Rate |
|------|-----------|-------|-------|-----------|
"""
        for i, t in enumerate(technique_ranking, 1):
            report += f"| {i} | {t['technique']} | {t['tests']} | {t['leaks']} | {t['leak_rate']*100:.1f}% |\n"
        
        # Write to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(report)
        
        print(f"✓ Report written to {output_path}")

def print_summary(aggregator: MetricsAggregator):
    """Print summary to console."""
    summary = aggregator.get_summary()
    
    print("\n" + "="*60)
    print("EVALUATION SUMMARY")
    print("="*60)
    print(f"Total Valid Tests:  {summary['total_tests']}")
    if summary.get("total_errors"):
        print(f"API Errors Skipped: {summary['total_errors']}")
    print(f"Successful Leaks:   {summary['successful_leaks']}")
    print(f"Leak Rate:          {summary['leak_rate']*100:.1f}%")
    print(f"Avg Turns to Leak:  {summary['avg_turns_to_leak']:.1f}")
    print("="*60)
