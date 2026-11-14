#!/usr/bin/env python3
"""
Comprehensive analysis of all Claude attack test results across versions and models.
"""

import json
import glob
from pathlib import Path


def load_results_file(filepath):
    """Load a single results file."""
    with open(filepath) as f:
        return json.load(f)


def analyze_all():
    """Analyze all available results files."""
    
    # Find all result files
    log_dir = Path("./auto_eval/logs")
    result_files = sorted(log_dir.glob("claude_novel*.json"))
    
    print("=" * 80)
    print("COMPREHENSIVE CLAUDE ATTACK RESULTS ANALYSIS")
    print("=" * 80)
    
    # Organize by version and model
    versions = {}
    for f in result_files:
        filename = f.name
        # Extract version and model from filename
        if "claude_novel_" in filename and "_claude-" in filename:
            # Determine version
            if "_v2_" in filename:
                version = "v2"
            elif "_v4_" in filename:
                version = "v4"
            elif "_v5_" in filename:
                version = "v5"
            else:
                version = "v1"
            
            # Determine model
            if "haiku-5-5" in filename:
                model = "haiku-5.5"
            elif "sonnet-5-5" in filename:
                model = "sonnet-5.5"
            elif "opus-5-5" in filename:
                model = "opus-5.5"
            else:
                continue
            
            if version not in versions:
                versions[version] = {}
            
            try:
                data = load_results_file(f)
                versions[version][model] = {
                    "file": str(f),
                    "summary": data.get("summary", {}),
                    "technique_ranking": data.get("technique_ranking", []),
                    "results": data.get("results", [])
                }
            except Exception as e:
                print(f"Error loading {f}: {e}")
    
    # Print summary table
    print("\nLEAK RATE COMPARISON:")
    print("-" * 80)
    print(f"{'Version':<10} {'Haiku-5.5':<12} {'Sonnet-5.5':<12} {'Opus-5.5':<12}")
    print("-" * 80)
    
    for version in sorted(versions.keys()):
        haiku_rate = versions[version].get("haiku-5.5", {}).get("summary", {}).get("leak_rate", 0)
        sonnet_rate = versions[version].get("sonnet-5.5", {}).get("summary", {}).get("leak_rate", 0)
        opus_rate = versions[version].get("opus-5.5", {}).get("summary", {}).get("leak_rate", 0)
        
        print(f"{version:<10} {haiku_rate*100:.1f}%{'':<6} {sonnet_rate*100:.1f}%{'':<6} {opus_rate*100:.1f}%{'':<6}")
    
    # Analyze most effective techniques across all versions
    print("\n\nMOST EFFECTIVE TECHNIQUES (across all versions, sonnet-5.5):")
    print("-" * 80)
    
    technique_stats = {}
    for version, models in versions.items():
        if "sonnet-5.5" in models:
            for tech in models["sonnet-5.5"]["technique_ranking"]:
                tech_id = tech["technique"]
                if tech_id not in technique_stats:
                    technique_stats[tech_id] = {"total_leaks": 0, "total_tests": 0}
                technique_stats[tech_id]["total_leaks"] += tech.get("leaks", 0)
                technique_stats[tech_id]["total_tests"] += tech.get("tests", 0)
    
    # Sort by leak rate (only techniques with at least 2 tests total)
    effective = []
    for tech_id, stats in technique_stats.items():
        if stats["total_tests"] >= 2:
            rate = stats["total_leaks"] / stats["total_tests"]
            effective.append((tech_id, rate, stats["total_leaks"], stats["total_tests"]))
    
    effective.sort(key=lambda x: x[1], reverse=True)
    
    for tech_id, rate, leaks, tests in effective[:10]:
        print(f"  {tech_id}: {leaks}/{tests} ({rate*100:.1f}%)")
    
    # Analyze most effective techniques on haiku-5.5
    print("\n\nMOST EFFECTIVE TECHNIQUES (across all versions, haiku-5.5):")
    print("-" * 80)
    
    technique_stats_haiku = {}
    for version, models in versions.items():
        if "haiku-5.5" in models:
            for tech in models["haiku-5.5"]["technique_ranking"]:
                tech_id = tech["technique"]
                if tech_id not in technique_stats_haiku:
                    technique_stats_haiku[tech_id] = {"total_leaks": 0, "total_tests": 0}
                technique_stats_haiku[tech_id]["total_leaks"] += tech.get("leaks", 0)
                technique_stats_haiku[tech_id]["total_tests"] += tech.get("tests", 0)
    
    effective_haiku = []
    for tech_id, stats in technique_stats_haiku.items():
        if stats["total_tests"] >= 2:
            rate = stats["total_leaks"] / stats["total_tests"]
            effective_haiku.append((tech_id, rate, stats["total_leaks"], stats["total_tests"]))
    
    effective_haiku.sort(key=lambda x: x[1], reverse=True)
    
    for tech_id, rate, leaks, tests in effective_haiku[:10]:
        print(f"  {tech_id}: {leaks}/{tests} ({rate*100:.1f}%)")


if __name__ == "__main__":
    analyze_all()
