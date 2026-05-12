#!/usr/bin/env python3
"""Validate the prompt set for a given version. Run by CI on every push.

Usage
-----
    python scripts/validate_prompts.py            # validates v1.0
    python scripts/validate_prompts.py 1.1        # validates v1.1
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from refusalbench.prompts import PromptValidationError, load_paired_sets, load_prompts


def main(version: str = "1.0") -> int:
    try:
        prompts = load_prompts(version)
        sets = load_paired_sets(version)
        placeholder_count = sum(
            1 for p in prompts if p.notes and "synthetic placeholder" in p.notes
        )
        print(f"v{version}: {len(prompts)} prompts, {len(sets)} paired sets loaded OK")
        if placeholder_count:
            print(
                f"WARNING: {placeholder_count} synthetic placeholder(s) found. "
                "Replace before running a real sweep.",
                file=sys.stderr,
            )
        return 0
    except (PromptValidationError, FileNotFoundError) as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "1.0"
    sys.exit(main(version))
