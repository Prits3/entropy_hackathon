#!/usr/bin/env python3
"""
Quick validation script for AutoEval logging system.
Run this after any sweep to verify logs are complete and well-formed.
"""

import json
from pathlib import Path
from datetime import datetime

LOG_DIR = Path(__file__).parent / "logs"


def validate_jsonl(filepath: Path) -> tuple[bool, str]:
    """Validate that a JSONL file has valid JSON on each line."""
    if not filepath.exists():
        return False, f"File not found: {filepath}"
    
    errors = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {i}: {e}")
    
    if errors:
        return False, f"{len(errors)} JSON errors found:\n  " + "\n  ".join(errors[:5])
    return True, "Valid JSONL"


def check_required_fields(filepath: Path) -> tuple[bool, str]:
    """Check that expected fields are present in sample records."""
    if not filepath.exists():
        return False, f"File not found: {filepath}"
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f][:10]  # Get first 10 lines
        
        for i, line in enumerate(lines, 1):
            if not line:
                continue
            record = json.loads(line)
            
            if filepath.name == "eval_turns.jsonl":
                required = ["ts", "type", "conversation_id", "model", "request", "response"]
            elif filepath.name == "sweeper_results.jsonl":
                required = ["ts", "type", "test_id", "technique", "success"]
            elif filepath.name in ("trainer_analysis.jsonl", "trainer_comprehensive.jsonl"):
                required = ["ts", "type"]
            else:
                required = ["ts", "type"]
            
            missing = [f for f in required if f not in record]
            if missing:
                return False, f"Missing fields on line {i}: {missing}"
    
    return True, "All required fields present"


def main():
    print("=" * 70)
    print(" AUTOEVAL LOGGING SYSTEM VALIDATION")
    print("=" * 70)
    
    # Check directory exists and is writable
    if not LOG_DIR.exists():
        print(f"\n❌ ERROR: Log directory not found: {LOG_DIR}")
        return 1
    
    print(f"\n✓ Log directory exists: {LOG_DIR}")
    
    # Validate each JSONL file
    jsonl_files = list(LOG_DIR.glob("*.jsonl"))
    
    if not jsonl_files:
        print("\n⚠️  No JSONL files found in log directory.")
        print("   Run a sweep first to generate logs.")
        return 1
    
    print(f"\nFound {len(jsonl_files)} JSONL file(s):")
    
    all_valid = True
    for filepath in sorted(jsonl_files):
        print(f"\n  📄 {filepath.name}")
        
        # Validate JSON format
        valid, msg = validate_jsonl(filepath)
        if not valid:
            print(f"     ❌ JSON validation failed: {msg}")
            all_valid = False
        else:
            print(f"     ✓ {msg}")
        
        # Check required fields
        valid, msg = check_required_fields(filepath)
        if not valid:
            print(f"     ❌ Field check failed: {msg}")
            all_valid = False
        else:
            print(f"     ✓ {msg}")
        
        # Show file size and line count
        stat = filepath.stat()
        lines = sum(1 for _ in open(filepath))
        print(f"     Size: {stat.st_size:,} bytes | Lines: {lines:,}")
    
    # Summary statistics
    total_size = sum(f.stat().st_size for f in jsonl_files)
    total_lines = sum(sum(1 for _ in open(f)) for f in jsonl_files)
    
    print("\n" + "=" * 70)
    if all_valid:
        print(" ✅ LOGGING SYSTEM VALIDATION PASSED")
    else:
        print(" ❌ LOGGING SYSTEM VALIDATION FAILED")
    print("=" * 70)
    
    print(f"\nSummary:")
    print(f"  Files validated: {len(jsonl_files)}")
    print(f"  Total size:      {total_size:,} bytes")
    print(f"  Total lines:     {total_lines:,}")
    
    # Latest timestamps
    if jsonl_files:
        latest_ts = None
        for filepath in jsonl_files:
            try:
                with open(filepath, 'r') as f:
                    last_line = json.loads(f.readline().strip())
                    ts = datetime.fromisoformat(last_line.get("ts", ""))
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
            except:
                pass
        
        if latest_ts:
            print(f"  Latest log entry: {latest_ts.strftime('%Y-%m-%d %H:%M:%S')}")
    
    return 0 if all_valid else 1


if __name__ == "__main__":
    exit(main())
