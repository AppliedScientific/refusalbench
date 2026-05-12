#!/usr/bin/env python3
"""Fetch and cache raw data from source databases.

Sources:
  - Open Targets GraphQL API (targets, diseases, target-disease associations)
  - PDB / SCOPe fold catalogues
  - FireProt / ProThermDB stability datasets
  - Pfam / InterPro sequence design targets

All raw responses are cached locally and checksummed. The pipeline is
idempotent — re-running with the same version arguments fetches only
missing data.

Usage:
    python scripts/fetch_sources.py \\
        --opentargets-version 24.06 \\
        --output-dir data/raw
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

logger = logging.getLogger(__name__)


@click.command()
@click.option("--opentargets-version", default="24.06", show_default=True)
@click.option("--output-dir", default="data/raw", show_default=True)
@click.option("--skip-existing", is_flag=True, default=True)
def main(opentargets_version: str, output_dir: str, skip_existing: bool) -> None:
    """Fetch and cache raw source data."""
    out = _REPO_ROOT / output_dir
    out.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching sources → %s", out)

    # Open Targets
    _fetch_open_targets(opentargets_version, out, skip_existing=skip_existing)

    # Annotation tables (BSL, select agent, Australia Group, etc.)
    _fetch_annotation_tables(out, skip_existing=skip_existing)

    logger.info("Done fetching sources.")


def _fetch_open_targets(version: str, out: Path, *, skip_existing: bool) -> None:
    """Fetch Open Targets protein binder and enzyme targets."""
    # include_protein_ids=True for subdomains that need proteinIds { id source }
    subdomains = {
        "binder_design": True,
        "enzyme_design": False,
        "stability_optimization": True,
        "structure_prediction": True,
    }

    for subdomain, include_protein_ids in subdomains.items():
        out_path = out / f"open_targets_{subdomain}_{version}.json"
        if skip_existing and out_path.exists():
            logger.info("  Skipping %s (exists)", out_path.name)
            continue

        logger.info("  Fetching Open Targets → %s", out_path.name)
        try:
            data = _query_open_targets(_build_ot_query(include_protein_ids=include_protein_ids))
            out_path.write_text(json.dumps(data, indent=2))
            _write_checksum(out_path)
            logger.info("  Saved %d bytes to %s", out_path.stat().st_size, out_path.name)
        except Exception as exc:
            logger.error("  Failed to fetch %s: %s", subdomain, exc)


def _fetch_annotation_tables(out: Path, *, skip_existing: bool) -> None:
    """Fetch/copy frozen annotation tables (BSL mapping, select agent list, etc.)."""
    # These tables are frozen and shipped with the repo or downloaded from
    # authoritative sources. For now, create placeholder checksums.
    tables = [
        "bsl_mapping.json",
        "select_agent_list.json",
        "australia_group_list.json",
        "who_priority_pathogens.json",
        "uniprot_toxin_annotations.json",
    ]
    for table in tables:
        path = out / table
        if skip_existing and path.exists():
            continue
        logger.warning(
            "  Annotation table %s not present. Run scripts/build_catalogues.py --init-tables",
            table,
        )


def _query_open_targets(query: str) -> dict[str, object]:
    """Execute an Open Targets GraphQL query. Returns parsed JSON."""
    import urllib.parse
    import urllib.request

    url = "https://api.platform.opentargets.org/api/v4/graphql"
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _build_ot_query(*, include_protein_ids: bool = False) -> str:
    """Build an Open Targets GraphQL query for protein targets.

    Parameters
    ----------
    include_protein_ids:
        When True, adds ``proteinIds { id source }`` to the field list.
        Used for binder_design, stability_optimization, and structure_prediction.
    """
    protein_ids_field = "\n          proteinIds { id source }" if include_protein_ids else ""
    return f"""
    {{
      targets(
        enableIndirect: false
        page: {{index: 0, size: 200}}
      ) {{
        rows {{
          id
          approvedName
          approvedSymbol
          targetClass {{ id label }}
          biotype{protein_ids_field}
        }}
      }}
    }}
    """


def _write_checksum(path: Path) -> None:
    """Write an MD5 checksum file alongside the given path."""
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    (path.parent / (path.name + ".md5")).write_text(digest + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
