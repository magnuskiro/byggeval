#!/usr/bin/env python3
"""
Enkelt startskript for å hente byggesaker fra Tønsberg kommune.
"""

import sys
import os

# Legg til src i PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from byggeval.fetch_cli import main

if __name__ == "__main__":
    main()
