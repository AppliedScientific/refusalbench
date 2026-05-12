"""Prompt loader + schema.

Each prompt JSON file in `prompts/v<version>/<tier>/` describes one
prompt. Prompts are organised in paired sets of three (benign,
borderline, dual_use) so refusal behavior can be compared on
matched-difficulty pairs.

Validation runs at load time and is repeated by `scripts/validate_prompts.py`
in CI:

  - Required fields present and well-typed
  - `subdomain` value is a registered enum member
  - `tier` value matches the directory it lives in
  - `paired_with` references resolve (every id in the tuple exists, is
    in a different tier, and points back to this prompt)
  - No duplicate prompt_id within a version
  - Every paired set spans exactly the three tiers

A `.frozen` marker file at `prompts/v<version>/.frozen` is the
preregistration commitment: once present, downstream tools must not
mutate the prompt set. The loader does not enforce this directly (it
loads either way) but exposes `is_frozen()` so scripts and tests can
reject mutations.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Default prompts root: <repo>/benchmark/prompts/. Tests override with tmp_path.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROMPTS_ROOT = _REPO_ROOT / "benchmark" / "prompts"


# ---------------------------------------------------------------------------
# Enums (single source of truth — JSONs validate against these at load time)
# ---------------------------------------------------------------------------


class Tier(StrEnum):
    BENIGN = "benign"
    BORDERLINE = "borderline"
    DUAL_USE = "dual_use"


class Subdomain(StrEnum):
    BINDER_DESIGN = "binder_design"
    ENZYME_DESIGN = "enzyme_design"
    DE_NOVO_PROTEIN = "de_novo_protein"
    STABILITY_OPTIMIZATION = "stability_optimization"
    SEQUENCE_DESIGN = "sequence_design"
    STRUCTURE_PREDICTION = "structure_prediction"
    BIOINFORMATICS_SCRIPTING = "bioinformatics_scripting"
    PROTOCOL_DESIGN = "protocol_design"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PromptValidationError(ValueError):
    """Raised when a prompt JSON fails schema validation at load time."""


class FrozenPromptSetError(RuntimeError):
    """Raised when callers attempt to mutate a frozen prompt set.

    The loader itself does not raise this; callers check `is_frozen(version)`
    and respect the marker. Scripts that mutate (freeze, unfreeze) reject
    accordingly.
    """


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Prompt:
    """One evaluation prompt.

    Attributes
    ----------
    prompt_id : str
        Globally unique within a prompt-set version.
    subdomain : Subdomain
        Registered enum value.
    tier : Tier
        BENIGN, BORDERLINE, or DUAL_USE — must match the directory the
        JSON lives in.
    paired_with : tuple[str, ...]
        Prompt IDs of the other two members of this paired set. Empty
        only for prompts that are intentionally unpaired (rare; flagged
        in the manuscript methods).
    prompt : str
        The verbatim text shown to the model.
    source_citation : str
        Where this prompt was derived from (paper title, dataset name,
        synthesis method). Required so the manuscript can cite.
    language : str
        ISO 639-1 code; "en" for the v1.0 English corpus.
    notes : str | None
        Free-form annotations. The string "synthetic placeholder" marks
        scaffold-stage stand-ins that must be replaced before a real
        sweep.
    provenance : dict[str, object] | None
        Internal provenance block written by the renderer (``_provenance``
        key in the JSON).  Not used for evaluation — only for auditing which
        source record and template produced each prompt.  ``None`` when the
        JSON was written before provenance tracking was added.
    """

    prompt_id: str
    subdomain: Subdomain
    tier: Tier
    paired_with: tuple[str, ...]
    prompt: str
    source_citation: str
    language: str
    notes: str | None = None
    provenance: dict[str, object] | None = None


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _version_dir(version: str, root: Path | None = None) -> Path:
    base = root or DEFAULT_PROMPTS_ROOT
    return base / f"v{version}"


def is_frozen(version: str, root: Path | None = None) -> bool:
    """Return True iff a `.frozen` marker exists for this prompt-set version."""
    return (_version_dir(version, root) / ".frozen").is_file()


def _validate_record(record: object, source: Path, expected_tier: Tier) -> Prompt:
    if not isinstance(record, dict):
        raise PromptValidationError(f"{source}: top-level value must be an object")
    required = {
        "prompt_id",
        "subdomain",
        "tier",
        "paired_with",
        "prompt",
        "source_citation",
        "language",
    }
    missing = required - set(record.keys())
    if missing:
        raise PromptValidationError(f"{source}: missing fields {sorted(missing)}")

    pid = record["prompt_id"]
    if not isinstance(pid, str) or not pid:
        raise PromptValidationError(f"{source}: prompt_id must be a non-empty string")

    try:
        subdomain = Subdomain(record["subdomain"])
    except ValueError as e:
        raise PromptValidationError(
            f"{source}: subdomain {record['subdomain']!r} is not registered. "
            f"Add it to the Subdomain enum or fix the JSON."
        ) from e

    try:
        tier = Tier(record["tier"])
    except ValueError as e:
        raise PromptValidationError(f"{source}: tier {record['tier']!r} is not registered.") from e
    if tier != expected_tier:
        raise PromptValidationError(
            f"{source}: tier in JSON ({tier.value}) does not match parent "
            f"directory ({expected_tier.value})"
        )

    paired = record["paired_with"]
    if not isinstance(paired, list) or not all(isinstance(p, str) for p in paired):
        raise PromptValidationError(f"{source}: paired_with must be a list of strings")

    text = record["prompt"]
    if not isinstance(text, str) or not text.strip():
        raise PromptValidationError(f"{source}: prompt must be a non-empty string")

    cite = record["source_citation"]
    if not isinstance(cite, str) or not cite.strip():
        raise PromptValidationError(f"{source}: source_citation must be non-empty")

    lang = record["language"]
    if not isinstance(lang, str) or not lang:
        raise PromptValidationError(f"{source}: language must be a non-empty string")

    notes = record.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise PromptValidationError(f"{source}: notes must be string or null")

    prov = record.get("_provenance")
    provenance: dict[str, object] | None = prov if isinstance(prov, dict) else None

    return Prompt(
        prompt_id=pid,
        subdomain=subdomain,
        tier=tier,
        paired_with=tuple(paired),
        prompt=text,
        source_citation=cite,
        language=lang,
        notes=notes,
        provenance=provenance,
    )


def load_prompts(version: str, root: Path | None = None) -> list[Prompt]:
    """Load every prompt JSON under `prompts/v<version>/<tier>/`.

    Validates schema, enum membership, tier-vs-directory consistency,
    paired-set integrity, and id uniqueness. Returns the prompts in
    deterministic order: sorted by (tier, subdomain, prompt_id).

    Raises
    ------
    PromptValidationError
        On any schema or referential failure. The message identifies
        the offending file.
    FileNotFoundError
        If `prompts/v<version>/` does not exist.
    """
    vdir = _version_dir(version, root)
    if not vdir.is_dir():
        raise FileNotFoundError(vdir)

    prompts: list[Prompt] = []
    for tier in Tier:
        tier_dir = vdir / tier.value
        if not tier_dir.is_dir():
            continue
        for path in sorted(tier_dir.glob("*.json")):
            with path.open() as f:
                record = json.load(f)
            prompts.append(_validate_record(record, path, tier))

    _check_unique_ids(prompts)
    _check_paired_sets(prompts)
    return sorted(prompts, key=lambda p: (p.tier.value, p.subdomain.value, p.prompt_id))


def _check_unique_ids(prompts: Iterable[Prompt]) -> None:
    seen: set[str] = set()
    for p in prompts:
        if p.prompt_id in seen:
            raise PromptValidationError(f"duplicate prompt_id: {p.prompt_id!r}")
        seen.add(p.prompt_id)


def _check_paired_sets(prompts: list[Prompt]) -> None:
    """Every non-empty paired_with reference must resolve and be reciprocal."""
    by_id = {p.prompt_id: p for p in prompts}
    for p in prompts:
        if not p.paired_with:
            continue
        for ref in p.paired_with:
            if ref not in by_id:
                raise PromptValidationError(
                    f"{p.prompt_id}: paired_with references unknown id {ref!r}"
                )
            target = by_id[ref]
            if target.tier == p.tier:
                raise PromptValidationError(
                    f"{p.prompt_id}: paired_with {ref!r} is in the same tier"
                )
            if p.prompt_id not in target.paired_with:
                raise PromptValidationError(
                    f"{p.prompt_id}: paired_with {ref!r} does not reciprocate"
                )


def load_paired_sets(version: str, root: Path | None = None) -> list[tuple[Prompt, Prompt, Prompt]]:
    """Return every paired set as an ordered (benign, borderline, dual_use) triple.

    A "paired set" is a maximal connected component over `paired_with`
    edges that spans exactly the three tiers. Sets that do not span
    all three tiers are an error (caller should use `load_prompts` if
    partial sets are intentional).
    """
    prompts = load_prompts(version, root)
    by_id = {p.prompt_id: p for p in prompts}

    # Connected components over paired_with
    seen: set[str] = set()
    sets: list[tuple[Prompt, Prompt, Prompt]] = []
    for p in prompts:
        if p.prompt_id in seen or not p.paired_with:
            continue
        component: set[str] = set()
        stack = [p.prompt_id]
        while stack:
            cur = stack.pop()
            if cur in component:
                continue
            component.add(cur)
            for ref in by_id[cur].paired_with:
                if ref not in component:
                    stack.append(ref)
        seen.update(component)
        members = [by_id[i] for i in component]
        tier_counts = {t: 0 for t in Tier}
        for m in members:
            tier_counts[m.tier] += 1
        if tier_counts != {t: 1 for t in Tier}:
            raise PromptValidationError(
                f"paired set {sorted(component)!r} does not span all three tiers; "
                f"got tier counts {tier_counts}"
            )
        triple = (
            next(m for m in members if m.tier == Tier.BENIGN),
            next(m for m in members if m.tier == Tier.BORDERLINE),
            next(m for m in members if m.tier == Tier.DUAL_USE),
        )
        sets.append(triple)
    sets.sort(key=lambda s: (s[0].subdomain.value, s[0].prompt_id))
    return sets
