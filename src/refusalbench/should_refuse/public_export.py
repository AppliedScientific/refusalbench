"""Public-safe export functions for the should-refuse module.

Every function in this module writes ONLY public-safe data (no prompt_text).
They are the authorised channel for updating metadata/ in the public repo tree.
"""

from __future__ import annotations

import csv
import logging
from datetime import UTC, datetime
from pathlib import Path

from refusalbench.should_refuse.generator import ShouldRefuseRecord

logger = logging.getLogger(__name__)

_MANIFEST_COLUMNS = [
    "prompt_id",
    "anchor_id",
    "subdomain",
    "template_id",
    "module",
    "sha256_hash",
    "criteria_C1",
    "criteria_C2",
    "criteria_C3",
    "criteria_C4",
    "criteria_C5",
    "review_status",
    "generated_at",
]

_REVIEW_LOG_COLUMNS = [
    "prompt_id",
    "anchor_id",
    "reviewer",
    "review_status",
    "review_notes",
    "approved_at",
]


def export_public_manifest(
    records: list[ShouldRefuseRecord],
    output_path: Path,
    *,
    overwrite: bool = False,
) -> None:
    """Write the public-safe manifest CSV (no prompt_text).

    Parameters
    ----------
    records:
        Records from ``ShouldRefuseGenerator.generate()``.
    output_path:
        Destination path — should be ``metadata/should_refuse_public_manifest.csv``
        in the public repo tree.
    overwrite:
        If False (default), raise if the file already contains data rows.
    """
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8").splitlines()
        has_data = len(existing) > 1  # more than just the header
        if has_data and not overwrite:
            raise FileExistsError(
                f"{output_path} already contains data.  Pass overwrite=True to replace."
            )

    # Safety: verify no record exposes prompt_text
    _assert_no_prompt_text_in_public_dicts(records)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_MANIFEST_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row = r.to_public_dict()
            writer.writerow(row)

    logger.info("Public manifest written → %s (%d records).", output_path, len(records))


def update_review_log(
    review_entries: list[dict[str, object]],
    log_path: Path,
    *,
    append: bool = True,
) -> None:
    """Append or overwrite review decisions to the public review log.

    Each entry in ``review_entries`` must have keys matching ``_REVIEW_LOG_COLUMNS``
    and must NOT include any raw prompt text.

    Parameters
    ----------
    review_entries:
        List of dicts with keys: prompt_id, anchor_id, reviewer, review_status,
        review_notes, approved_at.
        review_notes MUST NOT quote prompt text.
    log_path:
        Destination — should be ``metadata/should_refuse_review_log.csv``.
    append:
        If True (default), append to existing file rather than overwriting.
    """
    # Safety: ensure no entry contains prompt_text
    for entry in review_entries:
        if "prompt_text" in entry:
            raise ValueError(
                "review_entries must not contain 'prompt_text'. "
                "The review log is public-safe — strip prompt_text "
                "before calling update_review_log()."
            )

    mode = "a" if append and log_path.exists() else "w"
    write_header = mode == "w" or not log_path.exists()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open(mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_REVIEW_LOG_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for entry in review_entries:
            writer.writerow(entry)

    logger.info(
        "Review log %s → %s (%d entries).",
        "updated" if append else "written",
        log_path,
        len(review_entries),
    )


def make_review_entry(
    record: ShouldRefuseRecord,
    *,
    reviewer: str,
    review_status: str,
    review_notes: str = "",
) -> dict[str, object]:
    """Build a public-safe review log entry for a single record.

    Parameters
    ----------
    review_notes:
        Free-text reviewer notes.  Must NOT quote the full prompt text.
    """
    if review_status not in {"pending", "approved", "rejected"}:
        raise ValueError(
            f"review_status must be 'pending', 'approved', or 'rejected', got {review_status!r}"
        )
    # Warn if notes look like they contain prompt text
    if record.prompt_text and record.prompt_text[:30] in review_notes:
        raise ValueError(
            "review_notes appears to quote the prompt text.  "
            "Notes must remain public-safe — do not include verbatim prompt text."
        )
    return {
        "prompt_id": record.prompt_id,
        "anchor_id": record.anchor_id,
        "reviewer": reviewer,
        "review_status": review_status,
        "review_notes": review_notes,
        "approved_at": datetime.now(UTC).isoformat() if review_status == "approved" else "",
    }


def _assert_no_prompt_text_in_public_dicts(records: list[ShouldRefuseRecord]) -> None:
    """Raise if any public dict accidentally includes prompt_text."""
    for r in records:
        pub = r.to_public_dict()
        if "prompt_text" in pub:
            raise RuntimeError(
                f"PRIVACY VIOLATION: to_public_dict() for {r.prompt_id} contains "
                f"'prompt_text'.  This is a bug in generator.py."
            )
