#!/usr/bin/env python3
"""
Backwards-compatible entry point for the AutoEval dashboard.

The real implementation lives in auto_eval.run_dashboard — this file just
forwards to it so `python auto_eval/dashboard.py` keeps working.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_eval.run_dashboard import main

if __name__ == "__main__":
    sys.exit(main())
