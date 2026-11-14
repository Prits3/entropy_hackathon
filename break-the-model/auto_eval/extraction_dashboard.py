#!/usr/bin/env python3
"""
Backwards-compatible wrapper forwarding to the unified AutoEval HTML dashboard.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from auto_eval.run_dashboard import main

if __name__ == "__main__":
    argv = sys.argv[1:] if len(sys.argv) > 1 else ["--no-open"]
    sys.exit(main(argv))
