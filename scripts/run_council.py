#!/usr/bin/env python3
"""Run the council judge panel on a completed snapshot's eval CSVs.

Reads every CSV from results/snapshots/<label>/eval/, dispatches each
(prompt_id, model, trial_idx, response_text) tuple to the three-judge
council, and writes adjudicated results to:

    results/snapshots/<label>/council/adjudicated.csv

with columns:
    prompt_id, model, trial_idx, modal_compliance, modal_reason,
    compliance_agreement, reason_agreement, any_parse_failed,
    flagged_for_spot_check, subdomain, tier

Usage
-----
    python scripts/run_council.py --snapshot 2026-05
    python scripts/run_council.py --snapshot 2026-05 --demo   # mock judges
    python scripts/run_council.py --snapshot 2026-05 --resume # skip already-judged rows
"""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))


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
    import os
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

import click
import pandas as pd

from refusalbench.council import categorize, compute_krippendorff_alpha
from refusalbench.judges.mock import MockJudge
from refusalbench.prompts import load_prompts

_OUT_FIELDNAMES = [
    "prompt_id",
    "model",
    "trial_idx",
    "modal_compliance",
    "modal_reason",
    "compliance_agreement",
    "reason_agreement",
    "any_parse_failed",
    "flagged_for_spot_check",
    "subdomain",
    "tier",
]


def _load_prompt_meta(prompt_version: str) -> dict[str, dict]:
    """Return {prompt_id: {subdomain, tier}} from the frozen prompt set."""
    prompts = load_prompts(prompt_version)
    return {p.prompt_id: {"subdomain": p.subdomain, "tier": p.tier} for p in prompts}


def _load_completed(out_path: Path) -> set[tuple[str, str, int]]:
    if not out_path.exists():
        return set()
    done: set[tuple[str, str, int]] = set()
    with out_path.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                done.add((row["prompt_id"], row["model"], int(row["trial_idx"])))
            except (KeyError, ValueError):
                continue
    return done


async def _process_batch(
    rows: list[dict],
    judges: list,
    prompt_meta: dict[str, dict],
    out_path: Path,
    completed: set[tuple[str, str, int]],
    concurrency: int,
) -> tuple[int, list[str]]:
    write_header = not out_path.exists()
    written = 0
    judge_errors: list[str] = []
    sem = asyncio.Semaphore(concurrency)

    async def process_one(row: dict) -> None:
        nonlocal written, write_header
        key = (row["prompt_id"], row["model"], int(row["trial_idx"]))
        if key in completed:
            return
        response_text = row.get("response_text", "") or ""
        prompt_text = row.get("prompt_text", "")

        try:
            async with sem:
                result = await categorize(
                    prompt_id=row["prompt_id"],
                    prompt_text=prompt_text,
                    response_text=response_text,
                    judges=judges,
                )
        except Exception as exc:
            # A judge call failed (provider error, content-filtered judge input,
            # or network timeout).  Log the error and leave the row out of the
            # output CSV so --resume will retry it on the next run.
            msg = f"{row['prompt_id']} / {row['model']} / trial {row['trial_idx']}: {exc}"
            judge_errors.append(msg)
            return

        meta = prompt_meta.get(row["prompt_id"], {})
        out_row = {
            "prompt_id": result.prompt_id,
            "model": row["model"],
            "trial_idx": row["trial_idx"],
            "modal_compliance": result.modal_compliance,
            "modal_reason": result.modal_reason,
            "compliance_agreement": round(result.compliance_agreement, 4),
            "reason_agreement": round(result.reason_agreement, 4),
            "any_parse_failed": result.any_parse_failed,
            "flagged_for_spot_check": result.flagged_for_spot_check,
            "subdomain": meta.get("subdomain", ""),
            "tier": meta.get("tier", ""),
        }

        with out_path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_OUT_FIELDNAMES)
            if write_header:
                writer.writeheader()
                write_header = False
            writer.writerow(out_row)
        written += 1

    await asyncio.gather(*[process_one(r) for r in rows])
    return written, judge_errors


@click.command()
@click.option("--snapshot", required=True, metavar="YYYY-MM", help="Snapshot label.")
@click.option("--demo", is_flag=True, help="Use mock judges (no API keys needed).")
@click.option("--resume", is_flag=True, default=True, help="Skip already-judged rows (default: on).")
@click.option("--concurrency", default=4, show_default=True, help="Max parallel judge calls.")
@click.option("--prompt-version", default="1.0", show_default=True)
def main(
    snapshot: str,
    demo: bool,
    resume: bool,
    concurrency: int,
    prompt_version: str,
) -> None:
    """Run council categorization on a completed snapshot."""
    snap_dir = _PROJECT_ROOT / "results" / "snapshots" / snapshot
    eval_dir = snap_dir / "eval"
    council_dir = snap_dir / "council"
    out_path = council_dir / "adjudicated.csv"

    if not eval_dir.exists():
        click.echo(f"ERROR: {eval_dir} does not exist. Run the sweep first.", err=True)
        sys.exit(1)

    council_dir.mkdir(exist_ok=True)

    # Build judges
    if demo:
        judges = [
            MockJudge("mock_j1", "direct_refusal", "safety_policy"),
            MockJudge("mock_j2", "direct_refusal", "biosecurity_concern"),
            MockJudge("mock_j3", "compliance", "other"),
        ]
        click.echo("Demo mode: using mock judges.")
    else:
        from refusalbench.judges.llm_judge import build_judges_from_config
        judges = build_judges_from_config()
        click.echo(f"Council judges: {[j.judge_id for j in judges]}")

    # Load all eval CSVs
    eval_csvs = sorted(eval_dir.glob("*.csv"))
    if not eval_csvs:
        click.echo(f"ERROR: No CSVs found in {eval_dir}.", err=True)
        sys.exit(1)

    all_rows: list[dict] = []
    for csv_path in eval_csvs:
        df = pd.read_csv(csv_path)
        # Prompt text is not in the eval CSVs — we look it up from the prompt set
        all_rows.extend(df.to_dict(orient="records"))

    click.echo(f"Loaded {len(all_rows):,} rows from {len(eval_csvs)} eval CSVs.")

    # Load prompt metadata (subdomain, tier) and text
    prompt_meta = _load_prompt_meta(prompt_version)
    prompts_by_id = {p.prompt_id: p for p in load_prompts(prompt_version)}

    # Attach prompt_text from the frozen prompt set
    for row in all_rows:
        pid = row.get("prompt_id", "")
        row["prompt_text"] = prompts_by_id[pid].prompt if pid in prompts_by_id else ""

    completed: set[tuple[str, str, int]] = set()
    if resume and out_path.exists():
        completed = _load_completed(out_path)
        click.echo(f"Resuming: {len(completed):,} rows already adjudicated.")

    pending = [
        r for r in all_rows
        if (r["prompt_id"], r["model"], int(r["trial_idx"])) not in completed
    ]
    click.echo(f"Rows to adjudicate: {len(pending):,}")

    if not pending:
        click.echo("Nothing to do.")
        return

    written, judge_errors = asyncio.run(
        _process_batch(pending, judges, prompt_meta, out_path, completed, concurrency)
    )

    click.echo(f"\nDone. Wrote {written:,} new rows to {out_path}")

    if judge_errors:
        click.echo(
            f"\nWARNING: {len(judge_errors)} rows failed (judge error or content-filtered "
            "judge input). They are NOT in adjudicated.csv and will be retried on the "
            "next --resume run.",
            err=True,
        )
        for msg in judge_errors[:20]:
            click.echo(f"  {msg}", err=True)
        if len(judge_errors) > 20:
            click.echo(f"  ... and {len(judge_errors) - 20} more", err=True)
        # Write error log next to the output file for post-run inspection
        err_path = out_path.parent / "adjudicated_errors.txt"
        err_path.write_text("\n".join(judge_errors) + "\n")
        click.echo(f"Full error list written to {err_path}", err=True)

    # Quick agreement report (only if we have output rows to report on)
    if out_path.exists():
        df_out = pd.read_csv(out_path)
        refusal_rate = df_out["modal_compliance"].isin({"direct_refusal", "non_responsive"}).mean()
        flagged_rate = df_out["flagged_for_spot_check"].mean()
        parse_fail_rate = df_out["any_parse_failed"].mean()
        click.echo(f"Overall refusal rate  : {refusal_rate:.1%}")
        click.echo(f"Flagged for spot-check: {flagged_rate:.1%}")
        click.echo(f"Any parse failed      : {parse_fail_rate:.1%}")

    # Krippendorff alpha is not computed here (requires per-judge votes, not aggregated CSV)
    click.echo("\nNote: Krippendorff alpha requires per-judge vote data.")
    click.echo("Run scripts/run_pilot_categorization.py for agreement metrics on a pilot sample.")


if __name__ == "__main__":
    main()
