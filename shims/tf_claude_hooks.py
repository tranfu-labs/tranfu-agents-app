#!/usr/bin/env python3
"""Backward-compatible Claude-only entrypoint for tf_hooks.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tf_hooks


if __name__ == "__main__":
    raise SystemExit(tf_hooks.main(["--target", "claude"] + sys.argv[1:]))
