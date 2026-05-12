#!/usr/bin/env python3
"""Pre-commit hook: block any commit that would expose should-refuse prompt text.

Three independent checks are run on the staged file list:

  1. PATH CHECK — fail if any staged file lives under private_artifacts/.
     (Should never happen due to .gitignore, but belt-and-suspenders.)

  2. STRUCTURAL CHECK — fail if any staged JSON/CSV/YAML/MD file contains
     a "prompt_text" field alongside a "should_refuse" module marker.
     Catches the case where someone accidentally stages a private artifact.

  3. HASH CHECK (when private manifest is available) — fail if any staged
     file contains a 50-character leading fragment of any known should-refuse
     prompt.  Uses the private manifest at $REFUSALBENCH_PRIVATE_ARTIFACTS_DIR
     (or the default location relative to the repo root) to obtain the fragments.

Exit codes:
  0 — clean, commit may proceed
  1 — violation found, commit blocked

Install via .pre-commit-config.yaml (see repo root).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def _staged_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return [repo_root / p for p in result.stdout.splitlines() if p.strip()]


def check_path_not_private(staged: list[Path], repo_root: Path) -> list[str]:
    """Check 1: no staged file should live under private_artifacts/."""
    private_root = repo_root / "private_artifacts"
    violations = []
    for f in staged:
        try:
            f.relative_to(private_root)
            violations.append(f"STAGED PRIVATE FILE: {f.relative_to(repo_root)}")
        except ValueError:
            pass
    return violations


def check_no_structural_leak(staged: list[Path]) -> list[str]:
    """Check 2: no staged file contains prompt_text + should_refuse module marker."""
    _SCANNABLE = {".json", ".csv", ".yaml", ".yml", ".md", ".txt", ".html"}
    violations = []
    for f in staged:
        if f.suffix.lower() not in _SCANNABLE:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        has_module_marker = "should_refuse" in content
        has_prompt_text_field = '"prompt_text"' in content or "'prompt_text'" in content
        if has_module_marker and has_prompt_text_field:
            violations.append(
                f"STRUCTURAL LEAK: {f} contains 'should_refuse' module marker "
                f"AND 'prompt_text' field — likely a private artifact staged by mistake."
            )
    return violations


def _load_private_fragments() -> list[str]:
    """Load 50-char leading fragments from private manifest if available."""
    env_dir = os.environ.get("REFUSALBENCH_PRIVATE_ARTIFACTS_DIR")
    if not env_dir:
        return []

    manifest = (
        Path(env_dir).expanduser()
        / "should_refuse"
        / "v1.0"
        / "should_refuse_private_manifest.json"
    )
    if not manifest.exists():
        return []

    try:
        with manifest.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return [
            record["prompt_text"][:50]
            for record in data
            if record.get("prompt_text")
        ]
    except (json.JSONDecodeError, KeyError, OSError):
        return []


def check_no_fragment_leak(staged: list[Path]) -> list[str]:
    """Check 3: no staged file contains a known should-refuse prompt fragment."""
    fragments = _load_private_fragments()
    if not fragments:
        return []

    _SCANNABLE = {".json", ".csv", ".yaml", ".yml", ".md", ".txt", ".html", ".py", ".ipynb"}
    violations = []
    for f in staged:
        if f.suffix.lower() not in _SCANNABLE:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for fragment in fragments:
            if fragment in content:
                violations.append(
                    f"FRAGMENT LEAK: {f} contains a known should-refuse prompt fragment."
                )
                break  # one violation per file is enough

    return violations


def main() -> int:
    repo_root = _repo_root()
    staged = _staged_files(repo_root)

    if not staged:
        return 0

    all_violations: list[str] = []
    all_violations.extend(check_path_not_private(staged, repo_root))
    all_violations.extend(check_no_structural_leak(staged))
    all_violations.extend(check_no_fragment_leak(staged))

    if all_violations:
        print("\n╔══ COMMIT BLOCKED: should-refuse privacy violation ══╗", file=sys.stderr)
        for v in all_violations:
            print(f"║  {v}", file=sys.stderr)
        print(
            "╚═══════════════════════════════════════════════════╝\n"
            "Raw should-refuse prompt text must NEVER enter the public repo.\n"
            "Check that private artifacts are in a gitignored path outside the repo tree.\n",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
