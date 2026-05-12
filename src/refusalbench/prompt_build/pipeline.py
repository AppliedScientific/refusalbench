"""Template-based prompt rendering pipeline for paired sets and controls.

All prompt wording comes from deterministic template rendering.
No LLM rewriting is used or permitted.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from refusalbench.prompt_build.catalogue import CandidateRecord
from refusalbench.prompt_build.rendering import PromptRenderer, RenderError
from refusalbench.prompt_build.tier_rules import AssignedTier

logger = logging.getLogger(__name__)


def render_all(
    paired_records: list[tuple[CandidateRecord, CandidateRecord, CandidateRecord]],
    control_records: list[CandidateRecord],
    *,
    template_cfg_path: Path,
    seed: int = 42,
    source_version: str = "v1.0",
) -> list[dict[str, object]]:
    """Render all paired sets and controls into prompt dicts.

    Parameters
    ----------
    paired_records:
        List of (benign, borderline, dual_use) triples from
        :func:`~refusalbench.prompt_build.sampling.sample_paired_sets`.
    control_records:
        Benign-only control records from
        :func:`~refusalbench.prompt_build.sampling.sample_controls`.
    template_cfg_path:
        Path to ``config/template_config.json``.
    seed:
        Rendering seed passed to :class:`~refusalbench.prompt_build.rendering.PromptRenderer`.
    source_version:
        Written into each prompt's ``source_citation`` provenance.

    Returns
    -------
    list[dict[str, object]]
        Prompt dicts ready for JSON serialisation.

    Example
    -------
    >>> from pathlib import Path
    >>> prompts = render_all([], [], template_cfg_path=Path("config/template_config.json"))
    >>> prompts
    []
    """
    renderer = PromptRenderer(template_config_path=template_cfg_path, seed=seed)
    prompts: list[dict[str, object]] = []

    for benign, borderline, dual_use in paired_records:
        benign_id = _make_prompt_id(benign, "benign", seed)
        borderline_id = _make_prompt_id(borderline, "borderline", seed)
        dual_use_id = _make_prompt_id(dual_use, "dual_use", seed)

        for record, tier, prompt_id, partners in [
            (benign, AssignedTier.BENIGN, benign_id, [borderline_id, dual_use_id]),
            (borderline, AssignedTier.BORDERLINE, borderline_id, [benign_id, dual_use_id]),
            (dual_use, AssignedTier.DUAL_USE, dual_use_id, [benign_id, borderline_id]),
        ]:
            prompt_text = _render_or_skip(renderer, record, tier, prompt_id)
            if prompt_text is None:
                continue
            prompts.append(
                _build_prompt_dict(
                    prompt_id=prompt_id,
                    record=record,
                    tier=tier,
                    prompt_text=prompt_text,
                    paired_with=partners,
                    source_version=source_version,
                )
            )

    for record in control_records:
        ctrl_id = _make_prompt_id(record, "benign", seed)
        prompt_text = _render_or_skip(renderer, record, AssignedTier.BENIGN, ctrl_id)
        if prompt_text is None:
            continue
        prompts.append(
            _build_prompt_dict(
                prompt_id=ctrl_id,
                record=record,
                tier=AssignedTier.BENIGN,
                prompt_text=prompt_text,
                paired_with=[],
                source_version=source_version,
            )
        )

    return prompts


def _render_or_skip(
    renderer: PromptRenderer,
    record: CandidateRecord,
    tier: AssignedTier,
    prompt_id: str,
) -> str | None:
    try:
        return renderer.render(record, tier)
    except RenderError as exc:
        logger.warning("Skipping %s (render failed): %s", prompt_id, exc)
        return None


def _make_prompt_id(record: CandidateRecord, tier_name: str, seed: int) -> str:
    """Stable, content-derived ID — does not depend on iteration order."""
    raw = "\x1f".join([record.subdomain, tier_name, record.source_record_id, str(seed)])
    h = hashlib.blake2b(raw.encode(), digest_size=4).hexdigest()
    return f"{record.subdomain}_{tier_name}_{h}"


def _build_prompt_dict(
    *,
    prompt_id: str,
    record: CandidateRecord,
    tier: AssignedTier,
    prompt_text: str,
    paired_with: list[str],
    source_version: str,
) -> dict[str, object]:
    return {
        "prompt_id": prompt_id,
        "subdomain": record.subdomain,
        "tier": tier.value,
        "paired_with": paired_with,
        "prompt": prompt_text,
        "source_citation": _build_source_citation(record, source_version),
        "language": "en",
        "notes": None,
        "_provenance": {
            "source_record_id": record.source_record_id,
            "provenance_bundle_id": record.provenance_bundle_id,
            "source_database": record.source_database,
            "source_version": record.source_version,
            "target_name": record.target_name,
            "target_class": record.target_class,
            "organism_name": record.organism_name,
            "template_family": record.template_family,
        },
    }


def _build_source_citation(record: CandidateRecord, version: str) -> str:
    return (
        f"Derived from {record.source_database} ({record.source_version}); "
        f"target: {record.target_name}; organism: {record.organism_name}; "
        f"catalogue version {version}"
    )
