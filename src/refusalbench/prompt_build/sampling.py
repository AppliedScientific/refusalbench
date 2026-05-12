"""Stratified sampling of catalogue records into paired sets and controls.

All sampling is deterministic given the seed. Ratios and target counts
are read from ``config/sampling_config.json`` by the caller.

**Triple pairing invariant:** every (benign, borderline, dual_use) triple
must share the same ``provenance_bundle_id``. This guarantees that the
three prompts in a set represent the same scientific question at three
risk levels, rather than three unrelated records that happened to occupy
the same shuffled index.

The catalogue-building step is responsible for assigning the same
``provenance_bundle_id`` to records that belong together across tiers.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict

from refusalbench.prompt_build.catalogue import CandidateRecord
from refusalbench.prompt_build.tier_rules import TierAssignment

logger = logging.getLogger(__name__)


def sample_paired_sets(
    assigned: dict[str, list[tuple[CandidateRecord, TierAssignment]]],
    sampling_cfg: dict[str, object],
    *,
    seed: int = 42,
) -> list[tuple[CandidateRecord, CandidateRecord, CandidateRecord]]:
    """Sample (benign, borderline, dual_use) triples per subdomain.

    Triples are formed by grouping records that share the same
    ``provenance_bundle_id`` within a subdomain, then selecting bundles
    that have at least one record in each of the three tiers.  This
    ensures that each triple represents the same biological target at
    three risk levels, not three arbitrary records.

    Parameters
    ----------
    assigned:
        Tier-assigned records from
        :func:`~refusalbench.prompt_build.tier_rules.load_and_assign_tiers`.
    sampling_cfg:
        Loaded ``config/sampling_config.json``.
    seed:
        RNG seed for reproducible sampling.

    Returns
    -------
    list[tuple[CandidateRecord, CandidateRecord, CandidateRecord]]
        One triple per sampled paired set.

    Example
    -------
    >>> pairs = sample_paired_sets({}, {}, seed=42)
    >>> pairs
    []
    """
    rng = random.Random(seed)
    raw_exp = sampling_cfg.get("experimental_subdomains", {})
    experimental: dict[str, object] = dict(raw_exp) if isinstance(raw_exp, dict) else {}
    pairs: list[tuple[CandidateRecord, CandidateRecord, CandidateRecord]] = []

    for subdomain, cfg in experimental.items():
        target_n = int(cfg.get("paired_sets", 0)) if isinstance(cfg, dict) else 0
        if target_n == 0:
            continue

        benign_pool = _filter_subdomain(assigned.get("benign", []), subdomain)
        borderline_pool = _filter_subdomain(assigned.get("borderline", []), subdomain)
        dual_use_pool = _filter_subdomain(assigned.get("dual_use", []), subdomain)

        # Group each pool by provenance_bundle_id
        benign_by_bundle = _group_by_bundle(benign_pool)
        borderline_by_bundle = _group_by_bundle(borderline_pool)
        dual_use_by_bundle = _group_by_bundle(dual_use_pool)

        # Find bundles with coverage across all three tiers
        valid_bundles = sorted(
            benign_by_bundle.keys() & borderline_by_bundle.keys() & dual_use_by_bundle.keys()
        )

        if not valid_bundles:
            logger.warning(
                "Subdomain %r: no bundles span all three tiers — "
                "check that provenance_bundle_id is set consistently across tiers. "
                "Skipping subdomain.",
                subdomain,
            )
            continue

        rng.shuffle(valid_bundles)
        n = min(target_n, len(valid_bundles))
        if n < target_n:
            logger.warning(
                "Subdomain %r: requested %d paired sets but only %d valid bundles available.",
                subdomain,
                target_n,
                n,
            )

        for bundle_id in valid_bundles[:n]:
            benign_candidates = benign_by_bundle[bundle_id]
            borderline_candidates = borderline_by_bundle[bundle_id]
            dual_use_candidates = dual_use_by_bundle[bundle_id]
            # Deterministic pick: sort by source_record_id, take first
            pairs.append(
                (
                    min(benign_candidates, key=lambda r: r.source_record_id),
                    min(borderline_candidates, key=lambda r: r.source_record_id),
                    min(dual_use_candidates, key=lambda r: r.source_record_id),
                )
            )

    return pairs


def sample_controls(
    assigned: dict[str, list[tuple[CandidateRecord, TierAssignment]]],
    sampling_cfg: dict[str, object],
    *,
    seed: int = 42,
) -> list[CandidateRecord]:
    """Sample benign-only control records.

    Parameters
    ----------
    assigned:
        Tier-assigned records.
    sampling_cfg:
        Loaded ``config/sampling_config.json``.
    seed:
        RNG seed (offset by 1 from paired-set seed to avoid correlation).

    Returns
    -------
    list[CandidateRecord]
        Benign records for control subdomains.

    Example
    -------
    >>> controls = sample_controls({}, {}, seed=42)
    >>> controls
    []
    """
    rng = random.Random(seed + 1)
    raw_ctrl = sampling_cfg.get("control_subdomains", {})
    controls_cfg: dict[str, object] = dict(raw_ctrl) if isinstance(raw_ctrl, dict) else {}
    controls: list[CandidateRecord] = []

    for subdomain, cfg in controls_cfg.items():
        target_n = int(cfg.get("benign_only", 0)) if isinstance(cfg, dict) else 0
        if target_n == 0:
            continue
        pool = _filter_subdomain(assigned.get("benign", []), subdomain)
        rng.shuffle(pool)
        controls.extend(pool[:target_n])

    return controls


def _filter_subdomain(
    tier_records: list[tuple[CandidateRecord, TierAssignment]],
    subdomain: str,
) -> list[CandidateRecord]:
    return [r for r, _ in tier_records if r.subdomain == subdomain]


def _group_by_bundle(records: list[CandidateRecord]) -> dict[str, list[CandidateRecord]]:
    """Group records by provenance_bundle_id."""
    groups: dict[str, list[CandidateRecord]] = defaultdict(list)
    for r in records:
        groups[r.provenance_bundle_id].append(r)
    return dict(groups)
