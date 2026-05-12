"""Tests for bundle_definitions.csv loading and provenance_bundle_id assignment."""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ is not a package; add it to sys.path for direct import
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from build_catalogues import _load_bundle_definitions

# ---------------------------------------------------------------------------
# _load_bundle_definitions
# ---------------------------------------------------------------------------


def test_load_bundle_definitions_missing_file_returns_empty(tmp_path: Path) -> None:
    result = _load_bundle_definitions(tmp_path / "nonexistent.csv")
    assert result == {}


def test_load_bundle_definitions_empty_file_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "bundles.csv"
    p.write_text(
        "bundle_id,subdomain,benign_target_id,borderline_target_id,dual_use_target_id,rationale\n"
    )
    result = _load_bundle_definitions(p)
    assert result == {}


def test_load_bundle_definitions_single_row(tmp_path: Path) -> None:
    p = tmp_path / "bundles.csv"
    p.write_text(
        "bundle_id,subdomain,benign_target_id,borderline_target_id,dual_use_target_id,rationale\n"
        "binder_001,binder_design,ENSG001,ENSG002,ENSG003,receptor binder\n"
    )
    result = _load_bundle_definitions(p)
    assert result["ENSG001"] == "binder_001"
    assert result["ENSG002"] == "binder_001"
    assert result["ENSG003"] == "binder_001"


def test_load_bundle_definitions_multiple_bundles(tmp_path: Path) -> None:
    p = tmp_path / "bundles.csv"
    p.write_text(
        "bundle_id,subdomain,benign_target_id,borderline_target_id,dual_use_target_id,rationale\n"
        "binder_001,binder_design,ENSG001,ENSG002,ENSG003,receptor binder\n"
        "binder_002,binder_design,ENSG004,ENSG005,ENSG006,enzyme inhibitor\n"
    )
    result = _load_bundle_definitions(p)
    assert result["ENSG001"] == "binder_001"
    assert result["ENSG004"] == "binder_002"
    assert len(result) == 6


def test_load_bundle_definitions_skips_blank_bundle_id(tmp_path: Path) -> None:
    p = tmp_path / "bundles.csv"
    p.write_text(
        "bundle_id,subdomain,benign_target_id,borderline_target_id,dual_use_target_id,rationale\n"
        ",binder_design,ENSG001,ENSG002,ENSG003,placeholder\n"
        "binder_001,binder_design,ENSG004,ENSG005,ENSG006,real bundle\n"
    )
    result = _load_bundle_definitions(p)
    assert "ENSG001" not in result
    assert result["ENSG004"] == "binder_001"


def test_load_bundle_definitions_handles_missing_target_ids(tmp_path: Path) -> None:
    """A row with only some target IDs populated still loads the non-empty ones."""
    p = tmp_path / "bundles.csv"
    p.write_text(
        "bundle_id,subdomain,benign_target_id,borderline_target_id,dual_use_target_id,rationale\n"
        "binder_001,binder_design,ENSG001,,ENSG003,partial\n"
    )
    result = _load_bundle_definitions(p)
    assert result["ENSG001"] == "binder_001"
    assert result["ENSG003"] == "binder_001"
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Integration: bundle lookup overrides provenance_bundle_id in OT catalogue
# ---------------------------------------------------------------------------


def test_build_ot_catalogue_uses_bundle_lookup(tmp_path: Path) -> None:
    """When a target_id appears in the bundle lookup, its provenance_bundle_id
    is the shared bundle_id, not the target_id itself."""
    import json

    from build_catalogues import _build_ot_catalogue

    raw = {
        "data": {
            "targets": {
                "rows": [
                    {"id": "ENSG001", "approvedSymbol": "GENE1", "targetClass": []},
                    {"id": "ENSG002", "approvedSymbol": "GENE2", "targetClass": []},
                    {"id": "ENSG_OTHER", "approvedSymbol": "OTHER", "targetClass": []},
                ]
            }
        }
    }
    raw_file = tmp_path / "ot_binder_design.json"
    raw_file.write_text(json.dumps(raw))

    bundle_lookup = {"ENSG001": "binder_001", "ENSG002": "binder_001"}
    records = _build_ot_catalogue(
        raw_file=raw_file,
        subdomain="binder_design",
        annotation_tables={},
        source_version="24.06",
        bundle_lookup=bundle_lookup,
    )

    by_id = {r["source_record_id"]: r for r in records}
    # Targets in the lookup share the bundle ID
    assert by_id["ENSG001"]["provenance_bundle_id"] == "binder_001"
    assert by_id["ENSG002"]["provenance_bundle_id"] == "binder_001"
    # Target not in the lookup falls back to its own target_id
    assert by_id["ENSG_OTHER"]["provenance_bundle_id"] == "ENSG_OTHER"


def test_build_ot_catalogue_no_lookup_falls_back_to_target_id(tmp_path: Path) -> None:
    """Without a bundle lookup, every record's bundle_id equals its target_id."""
    import json

    from build_catalogues import _build_ot_catalogue

    raw = {
        "data": {
            "targets": {"rows": [{"id": "ENSG001", "approvedSymbol": "GENE1", "targetClass": []}]}
        }
    }
    raw_file = tmp_path / "ot_binder_design.json"
    raw_file.write_text(json.dumps(raw))

    records = _build_ot_catalogue(
        raw_file=raw_file,
        subdomain="binder_design",
        annotation_tables={},
        source_version="24.06",
    )
    assert records[0]["provenance_bundle_id"] == "ENSG001"


# ---------------------------------------------------------------------------
# _build_pathogen_catalogue
# ---------------------------------------------------------------------------


def _pathogen_entry(
    accession: str = "P0DTC2",
    organism_bsl: int = 3,
    select_agent: bool = False,
    toxin: bool = False,
    subdomains: list[str] | None = None,
) -> dict[str, object]:
    return {
        "uniprot_accession": accession,
        "protein_name": f"Protein {accession}",
        "organism_name": "Test organism",
        "organism_bsl": organism_bsl,
        "select_agent": select_agent,
        "toxin": toxin,
        "australia_group": False,
        "who_priority_pathogen": False,
        "pandemic_potential": False,
        "target_class": "test class",
        "applicable_subdomains": subdomains if subdomains is not None else ["binder_design"],
        "natural_language_summary": f"Test summary for {accession}",
    }


def test_build_pathogen_catalogue_missing_file_returns_empty(tmp_path: Path) -> None:
    from build_catalogues import _build_pathogen_catalogue

    result = _build_pathogen_catalogue(tmp_path / "nonexistent.json", "binder_design")
    assert result == []


def test_build_pathogen_catalogue_filters_by_subdomain(tmp_path: Path) -> None:
    """Only entries whose applicable_subdomains includes the requested subdomain are returned."""
    import json

    from build_catalogues import _build_pathogen_catalogue

    entries = [
        _pathogen_entry("P0DTC2", subdomains=["binder_design"]),
        _pathogen_entry("P9WQP1", subdomains=["enzyme_design"]),
    ]
    f = tmp_path / "pathogen_targets.json"
    f.write_text(json.dumps(entries))

    result = _build_pathogen_catalogue(f, "binder_design")
    assert len(result) == 1
    assert result[0]["source_record_id"] == "P0DTC2"


def test_build_pathogen_catalogue_risk_bsl4_becomes_dual_use(tmp_path: Path) -> None:
    """A BSL-4 organism entry gets organism_bsl=4 in the risk dict."""
    import json

    from build_catalogues import _build_pathogen_catalogue

    entries = [_pathogen_entry("Q05320", organism_bsl=4, subdomains=["binder_design"])]
    f = tmp_path / "pathogen_targets.json"
    f.write_text(json.dumps(entries))

    records = _build_pathogen_catalogue(f, "binder_design")
    assert records[0]["risk"]["organism_bsl"] == 4


def test_build_pathogen_catalogue_select_agent_flag(tmp_path: Path) -> None:
    """select_agent=true in JSON maps to select_agent_flag=True in risk."""
    import json

    from build_catalogues import _build_pathogen_catalogue

    entries = [_pathogen_entry("P13423", select_agent=True, subdomains=["binder_design"])]
    f = tmp_path / "pathogen_targets.json"
    f.write_text(json.dumps(entries))

    records = _build_pathogen_catalogue(f, "binder_design")
    assert records[0]["risk"]["select_agent_flag"] is True


def test_build_pathogen_catalogue_bundle_lookup_applied(tmp_path: Path) -> None:
    """When a bundle lookup is provided, provenance_bundle_id is overridden."""
    import json

    from build_catalogues import _build_pathogen_catalogue

    entries = [_pathogen_entry("P0DTC2", subdomains=["binder_design"])]
    f = tmp_path / "pathogen_targets.json"
    f.write_text(json.dumps(entries))

    records = _build_pathogen_catalogue(f, "binder_design", bundle_lookup={"P0DTC2": "binder_001"})
    assert records[0]["provenance_bundle_id"] == "binder_001"


def test_build_pathogen_catalogue_no_lookup_falls_back_to_accession(tmp_path: Path) -> None:
    """Without a bundle lookup, provenance_bundle_id equals the UniProt accession."""
    import json

    from build_catalogues import _build_pathogen_catalogue

    entries = [_pathogen_entry("P0DTC2", subdomains=["binder_design"])]
    f = tmp_path / "pathogen_targets.json"
    f.write_text(json.dumps(entries))

    records = _build_pathogen_catalogue(f, "binder_design")
    assert records[0]["provenance_bundle_id"] == "P0DTC2"


def test_build_pathogen_catalogue_source_database_is_uniprot(tmp_path: Path) -> None:
    import json

    from build_catalogues import _build_pathogen_catalogue

    entries = [_pathogen_entry("P0DTC2", subdomains=["binder_design"])]
    f = tmp_path / "pathogen_targets.json"
    f.write_text(json.dumps(entries))

    records = _build_pathogen_catalogue(f, "binder_design")
    assert records[0]["source_database"] == "uniprot"
