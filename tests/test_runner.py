"""Tests for runner.py: resumption-safe sweep, dedup, atomic writes."""

from __future__ import annotations

import csv
from pathlib import Path

from refusalbench.providers.base import ProviderError
from refusalbench.providers.mock import MockProvider
from refusalbench.runner import _load_completed, run_sweep


async def test_run_sweep_creates_csv(tmp_prompts: Path, tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    provider = MockProvider("Test response.")
    n = await run_sweep(
        provider,
        "test-model",
        output,
        prompts_root=tmp_prompts,
        n_trials=1,
    )
    assert output.exists()
    assert n == 3  # 3 prompts x 1 trial


async def test_run_sweep_csv_has_correct_columns(tmp_prompts: Path, tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    provider = MockProvider("Test response.")
    await run_sweep(provider, "test-model", output, prompts_root=tmp_prompts, n_trials=1)
    with output.open() as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
    expected = {
        "prompt_id",
        "model",
        "trial_idx",
        "run_seed",
        "response_text",
        "latency_ms",
        "error",
    }
    assert expected.issubset(headers)


async def test_run_sweep_five_trials_per_prompt(tmp_prompts: Path, tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    provider = MockProvider("response")
    await run_sweep(provider, "model", output, prompts_root=tmp_prompts, n_trials=5)
    with output.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 * 5  # 3 prompts x 5 trials


async def test_run_sweep_resumption_skips_completed(tmp_prompts: Path, tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    provider = MockProvider("response")

    # First run: all 3 prompts x 2 trials
    n1 = await run_sweep(provider, "model", output, prompts_root=tmp_prompts, n_trials=2)
    assert n1 == 6

    # Second run with same output: should write 0 new rows
    n2 = await run_sweep(provider, "model", output, prompts_root=tmp_prompts, n_trials=2)
    assert n2 == 0


async def test_run_sweep_partial_resume(tmp_prompts: Path, tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    provider = MockProvider("response")

    # First run: 1 trial
    await run_sweep(provider, "model", output, prompts_root=tmp_prompts, n_trials=1)

    # Second run: 2 trials (adds 1 more per prompt)
    n2 = await run_sweep(provider, "model", output, prompts_root=tmp_prompts, n_trials=2)
    assert n2 == 3


async def test_run_sweep_dedup_includes_trial_idx(tmp_prompts: Path, tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    provider = MockProvider("response")
    await run_sweep(provider, "model", output, prompts_root=tmp_prompts, n_trials=3)

    completed = _load_completed(output)
    trial_indices = {key[2] for key in completed}
    assert trial_indices == {0, 1, 2}


def test_load_completed_empty_file(tmp_path: Path) -> None:
    assert _load_completed(tmp_path / "nonexistent.csv") == set()


def test_load_completed_parses_existing(tmp_path: Path) -> None:
    f = tmp_path / "results.csv"
    with f.open("w", newline="") as fp:
        w = csv.DictWriter(
            fp,
            fieldnames=[
                "prompt_id",
                "model",
                "trial_idx",
                "run_seed",
                "response_text",
                "latency_ms",
                "error",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "prompt_id": "p1",
                "model": "m1",
                "trial_idx": "0",
                "run_seed": "42",
                "response_text": "r",
                "latency_ms": "100",
                "error": "",
            }
        )
    completed = _load_completed(f)
    assert ("p1", "m1", 0) in completed


async def test_run_sweep_response_stored_in_csv(tmp_prompts: Path, tmp_path: Path) -> None:
    output = tmp_path / "results.csv"
    provider = MockProvider("distinctive response text")
    await run_sweep(provider, "model", output, prompts_root=tmp_prompts, n_trials=1)
    with output.open() as f:
        rows = list(csv.DictReader(f))
    assert all(row["response_text"] == "distinctive response text" for row in rows)


def test_load_completed_skips_malformed_rows(tmp_path: Path) -> None:
    """Lines with missing/invalid trial_idx are skipped silently."""
    f = tmp_path / "results.csv"
    with f.open("w", newline="") as fp:
        fp.write("prompt_id,model,trial_idx,run_seed,response_text,latency_ms,error\n")
        fp.write("p1,m1,0,42,r,100,\n")
        fp.write("p2,m1,bad_int,42,r,100,\n")  # ValueError path
        fp.write("p3,m1,,42,r,100,\n")  # ValueError path (empty int)
    completed = _load_completed(f)
    assert ("p1", "m1", 0) in completed
    assert len(completed) == 1


async def test_run_sweep_provider_error_stored_in_error_field(
    tmp_prompts: Path, tmp_path: Path
) -> None:
    """When provider raises, the error field is populated and no response_text."""

    class FailingProvider(MockProvider):
        async def complete(
            self, model: str, system: str, user: str, temperature: float, max_tokens: int
        ) -> str:
            raise ProviderError("network failure")

    output = tmp_path / "results.csv"
    await run_sweep(FailingProvider(), "model", output, prompts_root=tmp_prompts, n_trials=1)
    with output.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert all("network failure" in row["error"] for row in rows)
    assert all(row["response_text"] == "" for row in rows)
