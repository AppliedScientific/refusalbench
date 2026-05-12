"""Hard validators for the prompt construction pipeline.

These validators define whether a prompt can exist in v1.0.
A failed validator triggers deterministic resample, not LLM correction.

Validators are grouped:
  A. Schema validation
  B. Pair integrity
  C. Rendering integrity
  D. Distribution integrity
  E. Deduplication
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised when a prompt fails a hard validation rule."""


@dataclass
class ValidationResult:
    """Result of running hard validators on a prompt set.

    Parameters
    ----------
    passed:
        True iff all validators passed.
    errors:
        List of (prompt_id, rule_name, message) triples.
    warnings:
        Non-fatal issues (e.g. placeholder markers).
    """

    passed: bool
    errors: list[tuple[str, str, str]]
    warnings: list[tuple[str, str, str]]


class HardValidator:
    """Runs all hard validation rules on a candidate prompt set.

    Parameters
    ----------
    min_prompt_chars:
        Minimum rendered prompt length in characters.
    max_prompt_chars:
        Maximum rendered prompt length in characters.
    near_duplicate_threshold:
        Jaccard trigram similarity above which two prompts are flagged
        as near-duplicates.

    Examples
    --------
    >>> validator = HardValidator()
    >>> result = validator.validate_set([], [])
    >>> result.passed
    True
    """

    _PLACEHOLDER_PATTERN = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
    _SYNTHETIC_MARKER = "synthetic placeholder"

    def __init__(
        self,
        min_prompt_chars: int = 150,
        max_prompt_chars: int = 1200,
        near_duplicate_threshold: float = 0.85,
    ) -> None:
        self._min_chars = min_prompt_chars
        self._max_chars = max_prompt_chars
        self._dup_threshold = near_duplicate_threshold

    def validate_set(
        self,
        prompts: Sequence[Mapping[str, object]],
        paired_sets: list[list[str]],
    ) -> ValidationResult:
        """Run all hard validators on a list of prompt dicts.

        Parameters
        ----------
        prompts:
            List of prompt dicts (must have at minimum ``prompt_id``,
            ``prompt``, ``subdomain``, ``tier``, ``source_citation``).
        paired_sets:
            Each inner list is the prompt_ids of one paired set.

        Returns
        -------
        ValidationResult
        """
        errors: list[tuple[str, str, str]] = []
        warnings: list[tuple[str, str, str]] = []

        self._check_schema(prompts, errors)
        self._check_unique_ids(prompts, errors)
        self._check_pair_integrity(prompts, paired_sets, errors)
        self._check_rendering_integrity(prompts, errors, warnings)
        self._check_deduplication(prompts, errors)
        self._check_length_distribution(prompts, errors)
        self._check_vocabulary_leakage(prompts, warnings)

        return ValidationResult(passed=len(errors) == 0, errors=errors, warnings=warnings)

    # -------------------------------------------------------------------
    # A. Schema validation
    # -------------------------------------------------------------------

    def _check_schema(
        self,
        prompts: Sequence[Mapping[str, object]],
        errors: list[tuple[str, str, str]],
    ) -> None:
        required = {"prompt_id", "prompt", "subdomain", "tier", "source_citation", "language"}
        for p in prompts:
            pid = str(p.get("prompt_id", "<unknown>"))
            missing = required - set(p.keys())
            if missing:
                errors.append((pid, "schema.missing_fields", f"Missing: {sorted(missing)}"))
            if not str(p.get("source_citation", "")).strip():
                errors.append((pid, "schema.empty_source_citation", "source_citation is empty"))

    # -------------------------------------------------------------------
    # B. Pair integrity
    # -------------------------------------------------------------------

    def _check_pair_integrity(
        self,
        prompts: Sequence[Mapping[str, object]],
        paired_sets: list[list[str]],
        errors: list[tuple[str, str, str]],
    ) -> None:
        by_id = {str(p["prompt_id"]): p for p in prompts}
        expected_tiers = {"benign", "borderline", "dual_use"}
        for pair in paired_sets:
            tiers = {str(by_id[pid]["tier"]) for pid in pair if pid in by_id}
            if tiers != expected_tiers:
                label = str(pair)
                errors.append(
                    (
                        label,
                        "pair.missing_tier",
                        f"Paired set has tiers {tiers}, expected {expected_tiers}",
                    )
                )
            subdomains = {str(by_id[pid].get("subdomain", "")) for pid in pair if pid in by_id}
            if len(subdomains) > 1:
                errors.append(
                    (
                        str(pair),
                        "pair.subdomain_mismatch",
                        f"Subdomains differ within set: {subdomains}",
                    )
                )

    # -------------------------------------------------------------------
    # C. Rendering integrity
    # -------------------------------------------------------------------

    def _check_rendering_integrity(
        self,
        prompts: Sequence[Mapping[str, object]],
        errors: list[tuple[str, str, str]],
        warnings: list[tuple[str, str, str]],
    ) -> None:
        for p in prompts:
            pid = str(p.get("prompt_id", "<unknown>"))
            text = str(p.get("prompt", ""))
            if self._PLACEHOLDER_PATTERN.search(text):
                errors.append(
                    (pid, "rendering.unfilled_placeholder", "Prompt contains {placeholder}")
                )
            if len(text) < self._min_chars:
                errors.append(
                    (
                        pid,
                        "rendering.too_short",
                        f"Prompt has {len(text)} chars < {self._min_chars}",
                    )
                )
            if len(text) > self._max_chars:
                errors.append(
                    (pid, "rendering.too_long", f"Prompt has {len(text)} chars > {self._max_chars}")
                )
            notes = str(p.get("notes", "") or "")
            if self._SYNTHETIC_MARKER in notes:
                warnings.append(
                    (
                        pid,
                        "rendering.synthetic_placeholder",
                        "Prompt notes contain 'synthetic placeholder'",
                    )
                )

    # -------------------------------------------------------------------
    # D. Unique ID check
    # -------------------------------------------------------------------

    def _check_unique_ids(
        self,
        prompts: Sequence[Mapping[str, object]],
        errors: list[tuple[str, str, str]],
    ) -> None:
        seen: list[str] = [str(p.get("prompt_id", "")) for p in prompts]
        counts = Counter(seen)
        for pid, count in counts.items():
            if count > 1:
                errors.append((pid, "schema.duplicate_id", f"prompt_id appears {count} times"))

    # -------------------------------------------------------------------
    # E. Deduplication
    # -------------------------------------------------------------------

    def _check_deduplication(
        self,
        prompts: Sequence[Mapping[str, object]],
        errors: list[tuple[str, str, str]],
    ) -> None:
        texts = [(str(p.get("prompt_id", "")), str(p.get("prompt", ""))) for p in prompts]
        # Exact duplicates
        text_counts: Counter[str] = Counter(t for _, t in texts)
        for pid, text in texts:
            if text_counts[text] > 1:
                errors.append(
                    (pid, "dedup.exact_duplicate", "Exact prompt text appears more than once")
                )
        # Near-duplicate check (O(n^2), acceptable for n≤500)
        for i, (pid_i, text_i) in enumerate(texts):
            for pid_j, text_j in texts[i + 1 :]:
                sim = _jaccard_trigram(text_i, text_j)
                if sim >= self._dup_threshold:
                    errors.append(
                        (
                            pid_i,
                            "dedup.near_duplicate",
                            f"Jaccard similarity {sim:.2f} with {pid_j} >= {self._dup_threshold}",
                        )
                    )

    # -------------------------------------------------------------------
    # F. Length distribution by tier (KS test)
    # -------------------------------------------------------------------

    def _check_length_distribution(
        self,
        prompts: Sequence[Mapping[str, object]],
        errors: list[tuple[str, str, str]],
    ) -> None:
        """Fail if prompt length distributions differ significantly across tiers.

        Uses the two-sample KS statistic to detect systematic length differences
        that could act as a confound — e.g. if dual_use prompts are all shorter
        than benign prompts, a model might refuse on length alone.

        Only runs when scipy is available and each tier has ≥10 prompts.
        """
        try:
            from scipy.stats import ks_2samp
        except ImportError:
            return

        by_tier: dict[str, list[int]] = {}
        for p in prompts:
            tier = str(p.get("tier", ""))
            length = len(str(p.get("prompt", "")))
            by_tier.setdefault(tier, []).append(length)

        tiers = [t for t, lengths in by_tier.items() if len(lengths) >= 10]
        for i, tier_a in enumerate(tiers):
            for tier_b in tiers[i + 1 :]:
                stat, p_value = ks_2samp(by_tier[tier_a], by_tier[tier_b])
                if p_value < 0.05:
                    errors.append(
                        (
                            "_set",
                            "distribution.length_tier_confound",
                            f"KS test {tier_a} vs {tier_b}: "
                            f"stat={stat:.3f}, p={p_value:.4f} < 0.05 "
                            "— prompt lengths differ significantly across tiers",
                        )
                    )

    # -------------------------------------------------------------------
    # G. Vocabulary leakage by tier
    # -------------------------------------------------------------------

    def _check_vocabulary_leakage(
        self,
        prompts: Sequence[Mapping[str, object]],
        warnings: list[tuple[str, str, str]],
    ) -> None:
        """Warn if a token appears in ≥80% of one tier but <5% of all others.

        Such tokens act as tier markers — a model that learns them can
        predict tier without reading the actual biological content.
        """
        by_tier: dict[str, list[str]] = {}
        for p in prompts:
            tier = str(p.get("tier", ""))
            words = str(p.get("prompt", "")).lower().split()
            by_tier.setdefault(tier, []).extend(words)

        if len(by_tier) < 2:
            return

        # Per-tier token frequencies (fraction of prompts in that tier containing the token)
        tier_prompt_texts: dict[str, list[set[str]]] = {}
        for p in prompts:
            tier = str(p.get("tier", ""))
            word_set = set(str(p.get("prompt", "")).lower().split())
            tier_prompt_texts.setdefault(tier, []).append(word_set)

        tiers = list(tier_prompt_texts.keys())
        all_tokens: set[str] = {
            w for words_list in tier_prompt_texts.values() for s in words_list for w in s
        }

        for token in all_tokens:
            if len(token) < 4:
                continue
            freqs = {}
            for tier in tiers:
                prompts_in_tier = tier_prompt_texts[tier]
                if not prompts_in_tier:
                    continue
                freqs[tier] = sum(1 for s in prompts_in_tier if token in s) / len(prompts_in_tier)

            for tier, freq in freqs.items():
                other_freqs = [f for t, f in freqs.items() if t != tier]
                if freq >= 0.80 and all(f < 0.05 for f in other_freqs):
                    warnings.append(
                        (
                            "_set",
                            "distribution.vocabulary_leakage",
                            f"Token {token!r} appears in {freq:.0%} of {tier!r} prompts "
                            "but <5% of all other tiers — possible tier marker",
                        )
                    )


def _trigrams(text: str) -> set[str]:
    """Extract character trigrams from text (lowercased, normalized)."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return {normalized[i : i + 3] for i in range(len(normalized) - 2)}


def _jaccard_trigram(a: str, b: str) -> float:
    """Jaccard similarity between two texts based on character trigrams."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
