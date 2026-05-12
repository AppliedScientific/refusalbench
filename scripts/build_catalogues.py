#!/usr/bin/env python3
"""Build normalized candidate catalogues from raw source data.

For each subdomain, reads raw fetched data and produces a JSONL catalogue
where each line is a CandidateRecord dict (pre-tier-assignment).

Risk annotations are applied at this stage from frozen annotation tables:
  - BSL mapping
  - Select agent list
  - Australia Group list
  - WHO priority pathogen list
  - UniProt toxin annotations

Usage:
    python scripts/build_catalogues.py \\
        --raw-dir data/raw \\
        --output-dir data/catalogues \\
        --opentargets-version 24.06
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from refusalbench.prompt_build.catalogue import (  # noqa: E402
    CandidateRecord,
    RiskAnnotation,
    record_to_dict,
)

logger = logging.getLogger(__name__)

# Subdomains handled by Open Targets fetch
_OT_SUBDOMAINS = {
    "binder_design",
    "enzyme_design",
    "stability_optimization",
    "structure_prediction",
}

# Control subdomains with hand-curated task lists
_CONTROL_SUBDOMAINS = {
    "bioinformatics_scripting",
    "protocol_design",
}


_DEFAULT_BUNDLE_DEFINITIONS = _REPO_ROOT / "data" / "bundle_definitions.csv"
_DEFAULT_PATHOGEN_TARGETS = _REPO_ROOT / "data" / "raw" / "pathogen_targets.json"


@click.command()
@click.option("--raw-dir", default="data/raw", show_default=True)
@click.option("--output-dir", default="data/catalogues", show_default=True)
@click.option("--opentargets-version", default="24.06", show_default=True)
@click.option(
    "--bundle-definitions",
    "bundle_definitions_path",
    default=str(_DEFAULT_BUNDLE_DEFINITIONS),
    show_default=True,
    help="Path to bundle_definitions.csv mapping target IDs to research-question bundles.",
)
@click.option(
    "--pathogen-targets",
    "pathogen_targets_path",
    default=str(_DEFAULT_PATHOGEN_TARGETS),
    show_default=True,
    help="Path to pathogen_targets.json with curated BSL-2+ protein entries.",
)
@click.option(
    "--init-tables",
    is_flag=True,
    default=False,
    help="Initialize stub annotation tables if missing.",
)
def main(
    raw_dir: str,
    output_dir: str,
    opentargets_version: str,
    bundle_definitions_path: str,
    pathogen_targets_path: str,
    init_tables: bool,
) -> None:
    """Build normalized subdomain catalogues from raw source data."""
    raw_path = _REPO_ROOT / raw_dir
    out_path = _REPO_ROOT / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    if init_tables:
        _init_stub_annotation_tables(raw_path)

    annotation_tables = _load_annotation_tables(raw_path)
    bundle_lookup = _load_bundle_definitions(Path(bundle_definitions_path))
    if bundle_lookup:
        logger.info("Loaded %d bundle definitions", len(bundle_lookup))
    else:
        logger.warning(
            "No bundle definitions loaded from %s — "
            "provenance_bundle_id will equal target_id; "
            "sampling will produce zero triples until bundle_definitions.csv is populated.",
            bundle_definitions_path,
        )

    pathogen_file = Path(pathogen_targets_path)

    for subdomain in _OT_SUBDOMAINS:
        raw_file = raw_path / f"open_targets_{subdomain}_{opentargets_version}.json"
        ot_records: list[dict[str, object]] = []
        if raw_file.exists():
            ot_records = _build_ot_catalogue(
                raw_file=raw_file,
                subdomain=subdomain,
                annotation_tables=annotation_tables,
                source_version=opentargets_version,
                bundle_lookup=bundle_lookup,
            )
        else:
            logger.warning(
                "Missing raw file %s — OT records skipped for %s", raw_file.name, subdomain
            )
        pathogen_records = _build_pathogen_catalogue(
            pathogen_file=pathogen_file,
            subdomain=subdomain,
            bundle_lookup=bundle_lookup,
        )
        records = ot_records + pathogen_records
        _write_catalogue(records, out_path / f"{subdomain}.jsonl")
        logger.info(
            "Built %s: %d OT + %d pathogen records",
            subdomain,
            len(ot_records),
            len(pathogen_records),
        )

    for subdomain in {"de_novo_protein", "sequence_design"}:
        records = _build_structural_catalogue(subdomain, annotation_tables)
        _write_catalogue(records, out_path / f"{subdomain}.jsonl")
        logger.info("Built %s: %d records (structural catalogue)", subdomain, len(records))

    for subdomain in _CONTROL_SUBDOMAINS:
        records = _build_control_catalogue(subdomain)
        _write_catalogue(records, out_path / f"{subdomain}.jsonl")
        logger.info("Built %s: %d control records", subdomain, len(records))

    logger.info("Done building catalogues.")


def _build_ot_catalogue(
    raw_file: Path,
    subdomain: str,
    annotation_tables: dict[str, object],
    source_version: str,
    bundle_lookup: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build a subdomain catalogue from an Open Targets raw JSON file.

    Parameters
    ----------
    bundle_lookup:
        Maps target_id → bundle_id from ``data/bundle_definitions.csv``.
        When provided, records whose target_id appears in the lookup get the
        shared bundle_id, enabling the sampling layer to form valid triples.
        Records not in the lookup default to ``target_id`` as bundle_id
        (producing no triples, which is the correct honest result until the
        bundle table is populated).
    """
    with raw_file.open() as f:
        raw = json.load(f)

    rows = raw.get("data", {}).get("targets", {}).get("rows", [])
    records: list[dict[str, object]] = []
    for row in rows:
        target_id = str(row.get("id", ""))
        target_name = str(row.get("approvedSymbol", row.get("approvedName", target_id)))
        target_classes = row.get("targetClass", [])
        target_class = target_classes[0]["label"] if target_classes else "unknown"
        bundle_id = (bundle_lookup or {}).get(target_id, target_id)
        # Extract the primary Swiss-Prot accession from proteinIds if present
        uniprot_id: str | None = None
        for pid in (row.get("proteinIds") or []):
            if isinstance(pid, dict) and pid.get("source") == "uniprot_swissprot":
                uniprot_id = str(pid["id"])
                break
        record = CandidateRecord(
            source_record_id=target_id,
            provenance_bundle_id=bundle_id,
            subdomain=subdomain,
            target_name=target_name,
            target_class=target_class,
            organism_name="Homo sapiens",
            source_database="open_targets",
            source_version=source_version,
            natural_language_summary=(
                f"{target_class} target {target_name} (Open Targets {source_version})"
            ),
            risk=_annotate_risk(target_name, "Homo sapiens", annotation_tables),
            uniprot_id=uniprot_id,
        )
        records.append(record_to_dict(record))
    return records


def _build_pathogen_catalogue(
    pathogen_file: Path,
    subdomain: str,
    bundle_lookup: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build catalogue records from the hand-curated pathogen_targets.json file.

    Each entry in the JSON specifies ``applicable_subdomains``; only entries
    that list ``subdomain`` are included.  Risk annotations are taken directly
    from the curated fields (not inferred from annotation tables), since
    pathogen proteins are explicitly classified by their UniProt accession.

    Parameters
    ----------
    bundle_lookup:
        Maps UniProt accession → bundle_id from ``bundle_definitions.csv``.
        Entries absent from the lookup fall back to their own accession,
        producing no triples (correct until bundle_definitions.csv is updated).
    """
    if not pathogen_file.exists():
        logger.warning("Missing pathogen targets file %s — skipping", pathogen_file.name)
        return []

    with pathogen_file.open() as f:
        entries = json.load(f)

    records: list[dict[str, object]] = []
    for entry in entries:
        applicable: list[str] = entry.get("applicable_subdomains", [])
        if subdomain not in applicable:
            continue

        accession = str(entry["uniprot_accession"])
        protein_name = str(entry.get("protein_name", accession))
        organism_name = str(entry.get("organism_name", "unknown"))
        bsl_raw = entry.get("organism_bsl")
        organism_bsl = int(bsl_raw) if bsl_raw is not None else None

        risk = RiskAnnotation(
            organism_bsl=organism_bsl,
            select_agent_flag=bool(entry.get("select_agent", False)),
            toxin_flag=bool(entry.get("toxin", False)),
            australia_group_flag=bool(entry.get("australia_group", False)),
            who_priority_pathogen_flag=bool(entry.get("who_priority_pathogen", False)),
            pandemic_potential_flag=bool(entry.get("pandemic_potential", False)),
        )

        bundle_id = (bundle_lookup or {}).get(accession, accession)
        pf_raw = entry.get("pathogen_family")
        pathogen_family: str | None = str(pf_raw) if pf_raw else None

        record = CandidateRecord(
            source_record_id=accession,
            provenance_bundle_id=bundle_id,
            subdomain=subdomain,
            target_name=protein_name,
            target_class=str(entry.get("target_class", "pathogen protein")),
            organism_name=organism_name,
            source_database="uniprot",
            source_version="2024_05",
            natural_language_summary=str(entry.get("natural_language_summary", protein_name)),
            risk=risk,
            pathogen_family=pathogen_family,
            uniprot_id=accession,
        )
        records.append(record_to_dict(record))
    return records


def _build_structural_catalogue(
    subdomain: str,
    annotation_tables: dict[str, object],
) -> list[dict[str, object]]:
    """Stub catalogue for PDB/SCOPe-sourced subdomains."""
    return []


def _build_control_catalogue(subdomain: str) -> list[dict[str, object]]:
    """Build control subdomain records from a static task list."""
    tasks_file = _REPO_ROOT / "data" / "raw" / f"control_tasks_{subdomain}.json"
    if not tasks_file.exists():
        logger.warning("Missing control task file %s", tasks_file.name)
        return []
    with tasks_file.open() as f:
        tasks = json.load(f)
    records: list[dict[str, object]] = []
    for i, task in enumerate(tasks):
        record = CandidateRecord(
            source_record_id=f"{subdomain}_ctrl_{i:04d}",
            provenance_bundle_id=f"control_{subdomain}",
            subdomain=subdomain,
            target_name=str(task.get("task_name", f"task_{i}")),
            target_class="control",
            organism_name="in silico",
            source_database="hand_curated",
            source_version="v1.0",
            natural_language_summary=str(task.get("description", "")),
            risk=RiskAnnotation(organism_bsl=1),
            additional_fields={k: str(v) for k, v in task.items()},
        )
        records.append(record_to_dict(record))
    return records


def _annotate_risk(
    target_name: str,
    organism_name: str,
    annotation_tables: dict[str, object],
) -> RiskAnnotation:
    """Annotate risk flags from frozen ID-based tables.

    Matching is **exact** (case-insensitive, stripped) against canonical IDs
    in the annotation tables — not substring matching.  This prevents false
    positives such as "tox" matching Toxoplasma or "sepsis" matching unrelated
    genes.  The tables must ship as lists of canonical identifiers (UniProt
    accessions for proteins, exact organism names from authoritative sources).
    """
    sa_list: list[str] = annotation_tables.get("select_agent_list", [])  # type: ignore[assignment]
    who_list: list[str] = annotation_tables.get("who_priority_pathogens", [])  # type: ignore[assignment]
    toxin_list: list[str] = annotation_tables.get("uniprot_toxin_annotations", [])  # type: ignore[assignment]
    bsl_map: dict[str, int] = annotation_tables.get("bsl_mapping", {})  # type: ignore[assignment]

    name_norm = target_name.strip().lower()
    org_norm = organism_name.strip().lower()

    sa_set = {s.strip().lower() for s in sa_list}
    who_set = {w.strip().lower() for w in who_list}
    toxin_set = {t.strip().lower() for t in toxin_list}

    # BSL lookup: exact match on organism name (case-insensitive).
    # Default to 1 only when the organism is genuinely not in the table.
    bsl_map_norm: dict[str, int] = {k.strip().lower(): v for k, v in bsl_map.items()}
    organism_bsl = bsl_map_norm.get(org_norm, 1)

    return RiskAnnotation(
        organism_bsl=organism_bsl,
        select_agent_flag=(name_norm in sa_set or org_norm in sa_set),
        toxin_flag=name_norm in toxin_set,
        who_priority_pathogen_flag=org_norm in who_set,
    )


def _load_annotation_tables(raw_dir: Path) -> dict[str, object]:
    """Load frozen annotation tables from the raw data directory."""
    tables: dict[str, object] = {}
    for name, default in (
        ("select_agent_list", []),
        ("australia_group_list", []),
        ("who_priority_pathogens", []),
        ("uniprot_toxin_annotations", []),
        ("bsl_mapping", {}),
    ):
        path = raw_dir / f"{name}.json"
        if path.exists():
            with path.open() as f:
                tables[name] = json.load(f)
        else:
            tables[name] = default
    return tables


def _load_bundle_definitions(path: Path) -> dict[str, str]:
    """Load bundle_definitions.csv and return a target_id → bundle_id lookup.

    Each row maps three target IDs (benign, borderline, dual_use) to one
    shared bundle_id.  The lookup is used by ``_build_ot_catalogue`` to
    override ``provenance_bundle_id`` so the sampling layer can form valid
    triples.

    Returns an empty dict if the file does not exist or contains no data rows.
    """
    if not path.exists():
        return {}
    lookup: dict[str, str] = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bundle_id = row.get("bundle_id", "").strip()
            if not bundle_id:
                continue
            for col in ("benign_target_id", "borderline_target_id", "dual_use_target_id"):
                tid = row.get(col, "").strip()
                if tid:
                    lookup[tid] = bundle_id
    return lookup


def _write_catalogue(records: list[dict[str, object]], path: Path) -> None:
    """Write a list of record dicts to a JSONL file."""
    with path.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


_STUB_BSL_MAPPING = {
    "_comment": "Map exact organism name (case-insensitive) to BSL level 1-4. "
    "Populate from CDC/USDA select-agent list and ABSA BSL reference.",
    "Ebola virus": 4,
    "Marburg virus": 4,
    "Variola virus": 4,
    "Yersinia pestis": 3,
    "Mycobacterium tuberculosis": 3,
    "Bacillus anthracis": 3,
    "Burkholderia pseudomallei": 3,
    "Influenza A virus (H5N1)": 3,
    "SARS-CoV-2": 3,
    "HIV-1": 2,
    "Homo sapiens": 1,
}


def _init_stub_annotation_tables(raw_dir: Path) -> None:
    """Write stub annotation tables with example entries for development."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    tables: dict[str, object] = {
        "select_agent_list.json": [
            "_comment: list exact UniProt accessions or organism names "
            "from HHS/USDA select-agent list"
        ],
        "australia_group_list.json": [
            "_comment: list exact identifiers from Australia Group biological agent control list"
        ],
        "who_priority_pathogens.json": [
            "_comment: list exact organism names from WHO priority pathogen list 2024"
        ],
        "uniprot_toxin_annotations.json": [
            "_comment: list exact UniProt accessions with keyword KW-0800 (Toxin)"
        ],
        "bsl_mapping.json": _STUB_BSL_MAPPING,
    }
    for name, default in tables.items():
        path = raw_dir / name
        if not path.exists():
            path.write_text(json.dumps(default, indent=2))
            logger.info("Initialized stub table: %s", name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
