#!/usr/bin/env python3
"""
Backwards-compatible console summary wrapper forwarding to auto_eval.run_dashboard --text.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from auto_eval.run_dashboard import main

if __name__ == "__main__":
    sys.exit(main(["--text"]))
