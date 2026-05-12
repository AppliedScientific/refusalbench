#!/usr/bin/env python3
"""Sampling CLI — thin wrapper around refusalbench.prompt_build.sampling."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from refusalbench.prompt_build.sampling import (  # noqa: E402, F401
    sample_controls,
    sample_paired_sets,
)
