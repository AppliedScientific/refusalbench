"""CLI entrypoints registered in pyproject.toml.

These thin wrappers delegate to the underlying module CLIs so that
``pip install`` installs the named commands.
"""

from __future__ import annotations


def validate_prompts_main() -> None:
    """Entry point for ``refusalbench-validate-prompts``."""
    import sys

    from refusalbench.prompts import PromptValidationError, load_prompts

    version = sys.argv[1] if len(sys.argv) > 1 else "1.0"
    try:
        prompts = load_prompts(version)
        print(f"OK: {len(prompts)} prompts loaded for version {version}")
    except (PromptValidationError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def pilot_categorization_main() -> None:
    """Entry point for ``refusalbench-pilot-categorization``."""
    import sys

    print("Use: python scripts/run_pilot_categorization.py --help", file=sys.stderr)
    sys.exit(1)


def should_refuse_main() -> None:
    """Entry point for ``refusalbench-should-refuse``.

    Delegates to the should_refuse CLI click application so that the installed
    command is equivalent to ``python scripts/should_refuse_cli.py``.
    """
    import sys
    from pathlib import Path

    # Make sure the scripts/ directory is importable when running as an entry point
    scripts_dir = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from should_refuse_cli import main  # type: ignore[import-not-found]

    main()
