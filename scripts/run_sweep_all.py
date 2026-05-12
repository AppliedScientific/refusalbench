#!/usr/bin/env python3
"""Run the RefusalBench sweep and write results into a versioned snapshot directory.

Usage
-----
1. Add credentials to .env:
       AWS_SECRET_ACCESS_KEY=ABSK...       # Bedrock
       OPENROUTER_API_KEY=sk-or-...        # OpenRouter

2. Run the full sweep (snapshot label defaults to YYYY-MM of today):
       python scripts/run_sweep_all.py

3. Explicit snapshot label:
       python scripts/run_sweep_all.py --snapshot 2026-05

4. One provider only:
       python scripts/run_sweep_all.py --only bedrock
       python scripts/run_sweep_all.py --only openrouter

5. Dry-run — plan + cost estimate, zero API calls:
       python scripts/run_sweep_all.py --dry-run

6. Resume — already-completed (prompt_id, model, trial_idx) cells are skipped:
       python scripts/run_sweep_all.py --snapshot 2026-05   # same label resumes

Results land in:
    results/snapshots/<label>/
        manifest.json          run metadata + git SHA
        sweep_models.json      frozen copy of the model panel used
        council.json           frozen copy of the judge panel
        eval/                  one CSV per model
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv(env_path)
        return
    except ImportError:
        pass
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(display_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_")


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _data_provenance() -> dict:
    """SHA-256 of every annotation file in data/. Answers 'what data did this run against?'"""
    annotation_files = [
        "data/bundle_definitions.csv",
        "data/raw/pathogen_targets.json",
        "data/raw/bsl_mapping.json",
        "data/raw/select_agent_list.json",
        "data/raw/australia_group_list.json",
        "data/raw/who_priority_pathogens.json",
        "data/raw/uniprot_toxin_annotations.json",
        "data/raw/open_targets_binder_design_24.06.json",
        "data/raw/open_targets_enzyme_design_24.06.json",
        "data/raw/open_targets_stability_optimization_24.06.json",
        "data/raw/open_targets_structure_prediction_24.06.json",
    ]
    catalogue_files = sorted((_PROJECT_ROOT / "data" / "catalogues").glob("*.jsonl"))
    sha_map = {}
    for rel in annotation_files:
        p = _PROJECT_ROOT / rel
        sha_map[rel] = _sha256(p) if p.exists() else "missing"
    for p in catalogue_files:
        rel = str(p.relative_to(_PROJECT_ROOT))
        sha_map[rel] = _sha256(p)
    return {
        "uniprot_release": "2024_05",
        "open_targets_version": "24.06",
        "file_sha256": sha_map,
    }


def _has_bedrock_key() -> bool:
    if os.environ.get("BEDROCK_API_KEY", "").startswith("ABSK"):
        return True
    return os.environ.get("AWS_SECRET_ACCESS_KEY", "").startswith("ABSK")


def _has_openrouter_key() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", ""))


def _provider_available(provider: str) -> bool:
    return {"bedrock": _has_bedrock_key, "openrouter": _has_openrouter_key}.get(provider, lambda: False)()


def _make_provider(provider: str) -> object:
    from refusalbench.providers.bedrock import BedrockProvider
    from refusalbench.providers.openrouter import OpenRouterProvider
    if provider == "bedrock":
        return BedrockProvider()
    if provider == "openrouter":
        return OpenRouterProvider()
    raise ValueError(f"Unknown provider: {provider!r}")


def _estimate_cost(entry: dict, n_prompts: int, n_trials: int) -> float | None:
    pricing = entry.get("pricing_usd_per_mtok")
    if not pricing:
        return None
    calls = n_prompts * n_trials
    return calls * 350 / 1_000_000 * pricing["input"] + calls * 600 / 1_000_000 * pricing["output"]


# ---------------------------------------------------------------------------
# Snapshot infrastructure
# ---------------------------------------------------------------------------

def _snapshot_label(override: str | None) -> str:
    if override:
        return override
    return datetime.date.today().strftime("%Y-%m")


def _init_snapshot(label: str, runnable: list[dict], config: dict, n_prompts: int, n_trials: int, prompt_version: str, seed: int = 42) -> Path:
    """Create snapshot directory, write manifest and frozen configs. Return snapshot dir."""
    snap_dir = _PROJECT_ROOT / "results" / "snapshots" / label
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "eval").mkdir(exist_ok=True)
    (snap_dir / "council").mkdir(exist_ok=True)
    (snap_dir / "figures").mkdir(exist_ok=True)

    # Frozen config copies (only write if not already present — preserve across resumes)
    frozen_models = snap_dir / "sweep_models.json"
    if not frozen_models.exists():
        shutil.copy(_PROJECT_ROOT / "benchmark" / "config" / "sweep_models.json", frozen_models)

    frozen_council = snap_dir / "council.json"
    council_src = _PROJECT_ROOT / "benchmark" / "council" / "v1.1.json"
    if not frozen_council.exists() and council_src.exists():
        shutil.copy(council_src, frozen_council)

    # Manifest (write or update)
    manifest_path = snap_dir / "manifest.json"
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = {
        "snapshot_label": label,
        "started_at": existing.get("started_at", datetime.datetime.utcnow().isoformat() + "Z"),
        "completed_at": None,
        "prompt_version": f"v{prompt_version}",
        "council_version": "v1.1",
        "git_sha": existing.get("git_sha") or _git_sha(),
        "seed": seed,
        "n_prompts": n_prompts,
        "n_trials": n_trials,
        "total_invocations": n_prompts * n_trials * len(runnable),
        "data_provenance": existing.get("data_provenance") or _data_provenance(),
        "models": [
            {
                "model_id": m["model_id"],
                "display_name": m["display_name"],
                "provider": m["provider"],
                "organization": m.get("organization"),
                "jurisdiction": m.get("jurisdiction"),
                "role": m.get("role"),
            }
            for m in runnable
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return snap_dir


def _finalize_manifest(snap_dir: Path) -> None:
    manifest_path = snap_dir / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text())
    manifest["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    manifest_path.write_text(json.dumps(manifest, indent=2))


# ---------------------------------------------------------------------------
# Sweep logic
# ---------------------------------------------------------------------------

async def _run_one(entry: dict, eval_dir: Path, kwargs: dict) -> int:
    from refusalbench.runner import run_sweep
    provider = _make_provider(entry["provider"])
    output_path = eval_dir / f"{_slug(entry['display_name'])}.csv"
    print(f"\n[{entry['display_name']}] → {output_path.name}", flush=True)
    written = await run_sweep(provider, entry["model_id"], output_path, **kwargs)
    print(f"[{entry['display_name']}] done — {written} new rows", flush=True)
    return written


async def run_all(
    snapshot: str | None = None,
    only: str | None = None,
    dry_run: bool = False,
    n_trials: int = 5,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    concurrency: int = 8,
    model_concurrency: int = 1,
    seed: int = 42,
    prompt_version: str = "1.0",
) -> None:
    label = _snapshot_label(snapshot)
    config = json.loads((_PROJECT_ROOT / "benchmark" / "config" / "sweep_models.json").read_text())
    all_models = config["models"]
    models = [m for m in all_models if only is None or m["provider"] == only]

    if not models:
        print(f"No models matched provider filter: {only!r}", file=sys.stderr)
        sys.exit(1)

    missing: list[str] = []
    runnable: list[dict] = []
    for m in models:
        (runnable if _provider_available(m["provider"]) else missing).append(m)

    from refusalbench.prompts import load_prompts
    n_prompts = len(load_prompts(prompt_version))

    print(f"\nRefusalBench sweep  →  results/snapshots/{label}/")
    print(f"Prompts: {n_prompts}  Trials: {n_trials}  Models: {len(runnable)}  Invocations: {n_prompts * n_trials * len(runnable):,}")

    if missing:
        print(f"\n  SKIPPED (missing key): {', '.join(missing)}")
        print("  Set BEDROCK_API_KEY / OPENROUTER_API_KEY in .env to include them.")

    total_est = 0.0
    print(f"\n  {'Model':<32} {'Provider':<12} {'Est. cost':>10}")
    print(f"  {'-'*32} {'-'*12} {'-'*10}")
    for m in runnable:
        cost = _estimate_cost(m, n_prompts, n_trials)
        if cost is None:
            cost_str = "  (Bedrock*)"
        else:
            total_est += cost
            cost_str = f"      ${cost:.2f}"
        print(f"  {m['display_name']:<32} {m['provider']:<12} {cost_str}")

    print(f"\n  Estimated total: ~${total_est:.2f}  (* Bedrock models priced separately)")

    if dry_run:
        print("\nDry-run — no API calls made.")
        return

    if not runnable:
        print("\nNothing to run. Check .env credentials.", file=sys.stderr)
        sys.exit(1)

    snap_dir = _init_snapshot(label, runnable, config, n_prompts, n_trials, prompt_version, seed=seed)
    print(f"\nSnapshot initialised: {snap_dir}", flush=True)

    sweep_kwargs = dict(
        prompt_version=prompt_version,
        n_trials=n_trials,
        temperature=temperature,
        max_tokens=max_tokens,
        concurrency=concurrency,
        seed=seed,
    )

    total_written = 0
    errors: list[str] = []

    async def _run_one_safe(entry: dict) -> None:
        nonlocal total_written
        try:
            written = await _run_one(entry, snap_dir / "eval", sweep_kwargs)
            total_written += written
        except Exception as exc:
            msg = f"{entry['display_name']}: {exc}"
            print(f"\n  ERROR — {msg}", file=sys.stderr)
            errors.append(msg)

    # Run models in parallel batches of model_concurrency
    model_sem = asyncio.Semaphore(model_concurrency)

    async def _run_one_gated(entry: dict) -> None:
        async with model_sem:
            await _run_one_safe(entry)

    try:
        await asyncio.gather(*[_run_one_gated(entry) for entry in runnable])
    except KeyboardInterrupt:
        print("\nInterrupted — progress saved. Re-run with same --snapshot to resume.", file=sys.stderr)
        sys.exit(130)

    _finalize_manifest(snap_dir)
    print(f"\n{'='*52}")
    print(f"Sweep complete  →  results/snapshots/{label}/")
    print(f"Total new rows: {total_written:,}")
    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the RefusalBench sweep into a versioned snapshot directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--snapshot", default=None, metavar="YYYY-MM",
        help="Snapshot label (default: current YYYY-MM). Use same label to resume.",
    )
    parser.add_argument(
        "--only", choices=["bedrock", "openrouter"], default=None,
        help="Run only this provider's models.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--n-trials", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--model-concurrency", type=int, default=1,
        help="Number of models to run in parallel (default: 1 = sequential).",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--prompt-version", default="1.0")

    args = parser.parse_args()
    asyncio.run(run_all(
        snapshot=args.snapshot,
        only=args.only,
        dry_run=args.dry_run,
        n_trials=args.n_trials,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        concurrency=args.concurrency,
        model_concurrency=args.model_concurrency,
        seed=args.seed,
        prompt_version=args.prompt_version,
    ))


if __name__ == "__main__":
    main()
