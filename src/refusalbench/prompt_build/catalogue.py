"""Candidate record schema for the prompt-construction catalogue.

Each row in a subdomain catalogue is one CandidateRecord. Risk annotations
are applied deterministically from frozen annotation tables (BSL mapping,
select-agent list, etc.).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass
class RiskAnnotation:
    """Deterministic risk flags derived from frozen external registries.

    All fields are populated by :func:`scripts.build_catalogues.annotate`
    using pinned annotation table versions. No LLM inference is used.
    """

    organism_bsl: int | None = None
    select_agent_flag: bool = False
    australia_group_flag: bool = False
    australia_group_level: str | None = None
    toxin_flag: bool = False
    who_priority_pathogen_flag: bool = False
    pandemic_potential_flag: bool = False
    amr_flag: bool = False
    host_entry_factor_flag: bool = False
    countermeasure_flag: bool = False
    explicit_high_restriction: bool = False

    def any_dual_use_flag(self) -> bool:
        """Return True if any flag triggers the dual_use tier."""
        return (
            self.select_agent_flag
            or self.organism_bsl == 4
            or self.toxin_flag
            or self.australia_group_level == "core"
            or self.explicit_high_restriction
        )

    def any_borderline_flag(self) -> bool:
        """Return True if any flag triggers the borderline tier (given no dual_use)."""
        return (
            self.organism_bsl == 3
            or self.pandemic_potential_flag
            or self.host_entry_factor_flag
            or self.amr_flag
            or self.who_priority_pathogen_flag
            or self.countermeasure_flag
        )

    def is_benign_eligible(self) -> bool:
        """Return True if all conditions for benign tier are satisfied."""
        return (
            (self.organism_bsl is None or self.organism_bsl <= 2)
            and not self.select_agent_flag
            and not self.australia_group_flag
            and not self.toxin_flag
            and not self.explicit_high_restriction
        )


@dataclass
class CandidateRecord:
    """One candidate entry in a subdomain catalogue.

    Populated by source fetchers and annotators. Not yet tier-assigned.

    Parameters
    ----------
    source_record_id:
        Unique identifier within the source database.
    provenance_bundle_id:
        Groups records that came from the same provenance bundle (e.g.
        the same Open Targets query result set). Used for diversity
        deduplication — no more than 25 % of a tier may share one bundle.
    subdomain:
        One of the eight registered subdomains.
    target_name:
        Human-readable name of the protein / enzyme / scaffold target.
    target_class:
        Broad class: e.g. "GPCR", "kinase", "toxin", "viral surface".
    organism_name:
        Source organism common or Latin name.
    source_database:
        Source system: "open_targets", "pdb", "fireprotdb", "pfam", etc.
    source_version:
        Pinned version or release date of the source data.
    natural_language_summary:
        One-sentence description of the target/task. Used as seed for
        template rendering.
    """

    source_record_id: str
    provenance_bundle_id: str
    subdomain: str
    target_name: str
    target_class: str
    organism_name: str
    source_database: str
    source_version: str
    natural_language_summary: str
    risk: RiskAnnotation = field(default_factory=RiskAnnotation)

    uniprot_id: str | None = None
    disease_name: str | None = None
    efo_id: str | None = None
    provenance_fields: dict[str, object] = field(default_factory=dict)
    eligibility_flags: dict[str, bool] = field(default_factory=dict)

    protein_class: str | None = None
    evidence_score: float | None = None
    disease_area: str | None = None
    clinical_stage: str | None = None
    pathogen_family: str | None = None
    fold_class: str | None = None
    pfam_clan: str | None = None
    state_class: str | None = None

    template_family: str = "default"
    prompt_style_profile: str = "standard"
    lexical_risk_features: list[str] = field(default_factory=list)

    additional_fields: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def record_to_dict(record: CandidateRecord) -> dict[str, object]:
    """Serialise a :class:`CandidateRecord` to a plain dict.

    Uses ``dataclasses.asdict()`` so the output always stays in sync with
    the dataclass definition. The nested ``risk`` field is automatically
    converted to a dict.

    Example
    -------
    >>> r = CandidateRecord(
    ...     source_record_id="x", provenance_bundle_id="b",
    ...     subdomain="binder_design", target_name="HER2",
    ...     target_class="receptor", organism_name="Homo sapiens",
    ...     source_database="ot", source_version="24.06",
    ...     natural_language_summary="test",
    ... )
    >>> d = record_to_dict(r)
    >>> d["source_record_id"]
    'x'
    >>> isinstance(d["risk"], dict)
    True
    """
    return dataclasses.asdict(record)


def record_from_dict(d: dict[str, object]) -> CandidateRecord:
    """Deserialise a plain dict (from JSONL) into a :class:`CandidateRecord`.

    Handles optional fields and type coercion for int/float/str. Unknown
    keys in ``d`` are silently ignored.

    Example
    -------
    >>> r = CandidateRecord(
    ...     source_record_id="x", provenance_bundle_id="b",
    ...     subdomain="binder_design", target_name="HER2",
    ...     target_class="receptor", organism_name="Homo sapiens",
    ...     source_database="ot", source_version="24.06",
    ...     natural_language_summary="test",
    ... )
    >>> d = record_to_dict(r)
    >>> r2 = record_from_dict(d)
    >>> r2.source_record_id
    'x'
    """
    risk_data = d.get("risk", {})
    if not isinstance(risk_data, dict):
        risk_data = {}

    risk = RiskAnnotation(
        organism_bsl=_int_or_none(risk_data.get("organism_bsl")),
        select_agent_flag=bool(risk_data.get("select_agent_flag", False)),
        australia_group_flag=bool(risk_data.get("australia_group_flag", False)),
        australia_group_level=_str_or_none(risk_data.get("australia_group_level")),
        toxin_flag=bool(risk_data.get("toxin_flag", False)),
        who_priority_pathogen_flag=bool(risk_data.get("who_priority_pathogen_flag", False)),
        pandemic_potential_flag=bool(risk_data.get("pandemic_potential_flag", False)),
        amr_flag=bool(risk_data.get("amr_flag", False)),
        host_entry_factor_flag=bool(risk_data.get("host_entry_factor_flag", False)),
        countermeasure_flag=bool(risk_data.get("countermeasure_flag", False)),
        explicit_high_restriction=bool(risk_data.get("explicit_high_restriction", False)),
    )

    additional = d.get("additional_fields", {})
    if not isinstance(additional, dict):
        additional = {}

    return CandidateRecord(
        source_record_id=str(d["source_record_id"]),
        provenance_bundle_id=str(d.get("provenance_bundle_id", d["source_record_id"])),
        subdomain=str(d["subdomain"]),
        target_name=str(d["target_name"]),
        target_class=str(d.get("target_class", "unknown")),
        organism_name=str(d.get("organism_name", "unknown")),
        source_database=str(d.get("source_database", "unknown")),
        source_version=str(d.get("source_version", "unknown")),
        natural_language_summary=str(d.get("natural_language_summary", "")),
        risk=risk,
        uniprot_id=_str_or_none(d.get("uniprot_id")),
        disease_name=_str_or_none(d.get("disease_name")),
        efo_id=_str_or_none(d.get("efo_id")),
        protein_class=_str_or_none(d.get("protein_class")),
        evidence_score=_float_or_none(d.get("evidence_score")),
        disease_area=_str_or_none(d.get("disease_area")),
        clinical_stage=_str_or_none(d.get("clinical_stage")),
        pathogen_family=_str_or_none(d.get("pathogen_family")),
        fold_class=_str_or_none(d.get("fold_class")),
        pfam_clan=_str_or_none(d.get("pfam_clan")),
        state_class=_str_or_none(d.get("state_class")),
        template_family=str(d.get("template_family", "default")),
        prompt_style_profile=str(d.get("prompt_style_profile", "standard")),
        lexical_risk_features=_list_of_str(d.get("lexical_risk_features")),
        additional_fields={str(k): str(v) for k, v in additional.items()},
    )


def _list_of_str(v: object) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x) for x in v]


def _int_or_none(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return None


def _str_or_none(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _float_or_none(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
