"""Launcher. Run with pythonw.exe to stay console-free."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from powerwatcher.app import main

if __name__ == "__main__":
    sys.exit(main())
