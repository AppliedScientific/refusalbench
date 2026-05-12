#!/usr/bin/env python3
"""Tier assignment CLI — thin wrapper around refusalbench.prompt_build.tier_rules."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from refusalbench.prompt_build.tier_rules import (  # noqa: E402, F401
    AssignedTier,
    TierAssignment,
    assign_tier,
    load_and_assign_tiers,
)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Assign tiers to catalogue records.")
    parser.add_argument("input", help="Input JSONL catalogue file")
    parser.add_argument("--output", "-o", help="Output JSONL with tier assignments")
    args = parser.parse_args()

    records: list[object] = []
    with open(args.input) as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))

    assigned = load_and_assign_tiers(records)
    for tier, items in assigned.items():
        print(f"{tier}: {len(items)} records")

    if args.output:
        with open(args.output, "w") as out:
            for tier, items in assigned.items():
                for record, assignment in items:
                    row = {
                        "source_record_id": record.source_record_id,
                        "subdomain": record.subdomain,
                        "target_name": record.target_name,
                        "assigned_tier": tier,
                        "triggered_rules": list(assignment.triggered_rules),
                    }
                    out.write(json.dumps(row) + "\n")
