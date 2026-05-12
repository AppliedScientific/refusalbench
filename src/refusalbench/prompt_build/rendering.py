"""Deterministic template-based prompt rendering.

Prompt wording varies only through:
  - approved synonym tables (loaded from config/template_config.json)
  - deterministic field insertion from CandidateRecord fields
  - small controlled phrasing variants (indexed by seed-derived int)

No free-form LLM rewriting is used or permitted.
"""

from __future__ import annotations

import hashlib
import json
import string
from pathlib import Path
from typing import Any

from refusalbench.prompt_build.catalogue import CandidateRecord
from refusalbench.prompt_build.tier_rules import AssignedTier

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_TEMPLATE_CONFIG = _REPO_ROOT / "benchmark" / "config" / "template_config.json"


class RenderError(ValueError):
    """Raised when a prompt cannot be rendered from its template."""


class PromptRenderer:
    """Render prompts from CandidateRecord + AssignedTier using frozen templates.

    Parameters
    ----------
    template_config_path:
        Path to ``config/template_config.json``. Defaults to the repo copy.
    seed:
        Controls which synonym / phrasing variants are selected. Must be
        deterministic given (record_id, tier, seed).

    Examples
    --------
    >>> renderer = PromptRenderer()
    >>> renderer  # doctest: +ELLIPSIS
    <refusalbench.prompt_build.rendering.PromptRenderer object at ...>
    """

    def __init__(
        self,
        template_config_path: Path | None = None,
        seed: int = 42,
    ) -> None:
        path = template_config_path or _DEFAULT_TEMPLATE_CONFIG
        with path.open() as f:
            cfg: Any = json.load(f)
        self._seed = seed
        self._synonym_tables: dict[str, list[str]] = cfg.get("synonym_tables", {})
        self._phrasing_variants: dict[str, list[str]] = cfg.get("phrasing_variants", {})
        self._subdomain_templates: dict[str, dict[str, object]] = cfg.get("subdomain_templates", {})
        self._global_rules: dict[str, object] = cfg.get("global_rules", {})

    def render(
        self,
        record: CandidateRecord,
        tier: AssignedTier,
        *,
        variant: str = "base",
    ) -> str:
        """Render a prompt for one (record, tier) pair.

        Parameters
        ----------
        record:
            A fully annotated CandidateRecord.
        tier:
            The assigned tier — controls which template variant is selected.
        variant:
            Template variant key within the subdomain template set.
            Defaults to ``"base"``.

        Returns
        -------
        str
            The rendered prompt text, validated against global rules.

        Raises
        ------
        RenderError
            If the subdomain has no template, the variant is missing, or
            the rendered text contains unfilled placeholders.
        """
        subdomain = record.subdomain
        if subdomain not in self._subdomain_templates:
            raise RenderError(f"No template for subdomain {subdomain!r}")

        tmpl_block = self._subdomain_templates[subdomain]
        if variant not in tmpl_block:
            variant = "base"
        template_str = str(tmpl_block[variant])

        # Build the substitution context from record fields + synonym selection
        ctx = self._build_context(record, tier)

        try:
            rendered = _safe_format(template_str, ctx)
        except KeyError as exc:
            raise RenderError(
                f"Template key {exc} missing in record {record.source_record_id}"
            ) from exc

        # Detect unfilled placeholders via the formatter (handles format specs / conversions)
        remaining = [fn for _, fn, _, _ in string.Formatter().parse(rendered) if fn is not None]
        if remaining:
            raise RenderError(
                f"Unfilled placeholders in prompt for {record.source_record_id}: {remaining}"
            )

        self._validate_global_rules(rendered)
        return rendered

    def _build_context(self, record: CandidateRecord, tier: AssignedTier) -> dict[str, str]:
        """Build the substitution context for template rendering."""

        # Deterministic synonym/phrasing selection.
        # Use "\x1f" (ASCII unit-separator) between fields to prevent
        # collisions like ("a1", "benign", "23") vs ("a", "1benign", "23").
        def pick(table_key: str) -> str:
            variants = self._synonym_tables.get(table_key, [table_key])
            seed_str = "\x1f".join([record.source_record_id, tier.value, str(self._seed)])
            idx = _stable_hash(seed_str) % len(variants)
            return variants[idx]

        def pick_phrasing(key: str) -> str:
            variants = self._phrasing_variants.get(key)
            if not variants:
                raise RenderError(f"Missing phrasing variant {key!r} — add to template_config.json")
            seed_str = "\x1f".join([record.source_record_id, key, str(self._seed)])
            idx = _stable_hash(seed_str) % len(variants)
            return variants[idx]

        ctx: dict[str, str] = {
            "target_name": record.target_name,
            "target_class": record.target_class,
            "organism_name": record.organism_name,
            "uniprot_id": record.uniprot_id or record.target_name,
            "disease_name": record.disease_name or "the relevant disease",
            "fold_class": record.fold_class or "mixed alpha-beta",
            "pfam_clan": record.pfam_clan or "the target family",
            "design_verb": pick("design_verb"),
            "affinity_descriptor": pick("affinity_descriptor"),
            "binding_metric": pick("binding_metric"),
            "output_verb": pick("output_verb"),
            "approach_noun": pick("approach_noun"),
            "computational_tool": pick("computational_tool"),
            "binder_type": pick("binder_type"),
            "stability_metric": pick("stability_metric"),
            "context_intro": pick_phrasing("context_intro"),
            "deliverable_suffix": pick_phrasing("deliverable_suffix"),
        }
        # Merge any additional fields from the record
        ctx.update(record.additional_fields)
        return ctx

    def _validate_global_rules(self, rendered: str) -> None:
        """Apply global rendering rules. Raises RenderError on violation."""
        rules = self._global_rules
        max_chars = int(rules.get("max_prompt_chars", 1200))  # type: ignore[call-overload]
        min_chars = int(rules.get("min_prompt_chars", 150))  # type: ignore[call-overload]
        if len(rendered) > max_chars:
            raise RenderError(f"Rendered prompt exceeds {max_chars} chars (got {len(rendered)})")
        if len(rendered) < min_chars:
            raise RenderError(f"Rendered prompt too short: {len(rendered)} < {min_chars} chars")


def _safe_format(template: str, ctx: dict[str, str]) -> str:
    """Format a string template, leaving unknown keys in place."""
    formatter = string.Formatter()
    result_parts = []
    for literal, field_name, format_spec, _conversion in formatter.parse(template):
        result_parts.append(literal)
        if field_name is not None:
            if field_name in ctx:
                value = ctx[field_name]
                result_parts.append(formatter.format_field(value, format_spec or ""))
            else:
                result_parts.append("{" + field_name + "}")
    return "".join(result_parts)


def _stable_hash(s: str) -> int:
    """Deterministic 32-bit hash using blake2b. Not Python's built-in (randomized)."""
    digest = hashlib.blake2b(s.encode(), digest_size=4).digest()
    return int.from_bytes(digest, "little")
