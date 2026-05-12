"""Should-refuse positive control module for RefusalBench.

This module generates exactly 15 prompts from dual_use-eligible anchors for use
as a positive-control calibration set alongside the main benchmark.

Privacy contract
────────────────
Raw prompt text is NEVER written to the public repository tree.  All rendered
prompt text is written exclusively to the private artifact path, configured via
the ``--private-artifacts-dir`` CLI flag or the
``REFUSALBENCH_PRIVATE_ARTIFACTS_DIR`` environment variable.

Public artifacts (IDs, hashes, criteria flags, review metadata) are written to
``metadata/`` in the public repository tree.

Public repo may contain
    - generation code (this module)
    - criteria/schema (benchmark/config/should_refuse_criteria.yaml)
    - template registry metadata (benchmark/templates.yaml)
    - public-safe manifest (results/should_refuse/should_refuse_public_manifest.csv)
    - review log (results/should_refuse/should_refuse_review_log.csv)

Public repo must NOT contain
    - rendered should-refuse prompt text
    - near-verbatim fragments of rendered prompt text
    - test fixtures embedding full prompt text
    - any export that includes prompt_text for this module
"""

from refusalbench.should_refuse.classifier import (
    NO_REFUSAL,
    REFUSAL,
    RefusalClassifier,
    classify,
)
from refusalbench.should_refuse.generator import ShouldRefuseGenerator, ShouldRefuseRecord
from refusalbench.should_refuse.public_export import export_public_manifest, update_review_log
from refusalbench.should_refuse.validators import ShouldRefuseValidator, ValidationResult

__all__ = [
    "NO_REFUSAL",
    "REFUSAL",
    "RefusalClassifier",
    "ShouldRefuseGenerator",
    "ShouldRefuseRecord",
    "ShouldRefuseValidator",
    "ValidationResult",
    "classify",
    "export_public_manifest",
    "update_review_log",
]
