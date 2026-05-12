"""Validators for the should-refuse positive control module.

Eight validators are implemented, each corresponding to a named invariant.
All validators operate on public-safe representations where possible; the
full-text validators (V3, V7, V8) receive prompt_text via a controlled
internal API and must never write it to tracked paths.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from refusalbench.should_refuse.generator import (
    _DISQUALIFYING_PATTERNS,
    TARGET_COUNT,
    ShouldRefuseRecord,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Outcome of a single validation check."""

    validator_id: str
    passed: bool
    message: str
    detail: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] {self.validator_id}: {self.message}"]
        for d in self.detail:
            lines.append(f"       {d}")
        return "\n".join(lines)


class ShouldRefuseValidator:
    """Runs all eight invariant checks against a generated should-refuse set.

    Parameters
    ----------
    public_prompts_root:
        Root of the public prompt tree (``prompts/v1.0/``).  Used by V3 to
        load the full public prompt text for overlap detection.
    repo_root:
        Repository root.  Used by V7 (git ls-files scan).
    scan_paths:
        Additional paths to scan for V8 (CI artifact directories, snapshot dirs).
        Defaults to ``snapshots/``, ``results/``, ``qc/``.
    """

    def __init__(
        self,
        public_prompts_root: Path | None = None,
        repo_root: Path | None = None,
        scan_paths: list[Path] | None = None,
    ) -> None:
        self._repo_root = repo_root or _default_repo_root()
        self._public_prompts_root = public_prompts_root or (
            self._repo_root / "benchmark" / "prompts"
        )
        self._scan_paths = scan_paths or [
            self._repo_root / "results" / "snapshots",
            self._repo_root / "results",
            self._repo_root / "results" / "qc",
        ]

    # ── Public API ───────────────────────────────────────────────────────────

    def validate_all(self, records: list[ShouldRefuseRecord]) -> list[ValidationResult]:
        """Run all eight validators and return results."""
        results = [
            self.v1_all_anchors_are_dual_use(records),
            self.v2_exact_count(records),
            self.v3_no_text_overlap_with_public(records),
            self.v4_no_defensive_framing(records),
            self.v5_deterministic_ids(records),
            self.v6_public_exports_have_no_prompt_text(records),
            self.v7_no_tracked_file_contains_prompt_text(records),
            self.v8_no_output_path_contains_prompt_text(records),
        ]
        passed = sum(1 for r in results if r.passed)
        logger.info("Validation: %d/%d checks passed.", passed, len(results))
        return results

    def all_pass(self, records: list[ShouldRefuseRecord]) -> bool:
        """Return True iff all validators pass."""
        return all(r.passed for r in self.validate_all(records))

    # ── Individual validators ────────────────────────────────────────────────

    def v1_all_anchors_are_dual_use(self, records: list[ShouldRefuseRecord]) -> ValidationResult:
        """V1: every anchor_id maps to a dual_use-tier benchmark prompt."""
        dual_use_dir = self._public_prompts_root / "v1.0" / "dual_use"
        if not dual_use_dir.exists():
            return ValidationResult(
                "V1",
                False,
                "dual_use prompt directory not found",
                [str(dual_use_dir)],
            )

        known_dual_use: set[str] = {p.stem for p in dual_use_dir.glob("*.json")}
        violations: list[str] = []
        for r in records:
            if r.anchor_id not in known_dual_use:
                violations.append(f"{r.prompt_id}: anchor_id={r.anchor_id!r} not in dual_use/")

        if violations:
            return ValidationResult(
                "V1",
                False,
                f"{len(violations)} anchor(s) not found in dual_use prompt set",
                violations,
            )
        return ValidationResult(
            "V1", True, f"All {len(records)} anchors confirmed dual_use eligible"
        )

    def v2_exact_count(self, records: list[ShouldRefuseRecord]) -> ValidationResult:
        """V2: exactly TARGET_COUNT (15) prompts generated."""
        n = len(records)
        if n != TARGET_COUNT:
            return ValidationResult(
                "V2",
                False,
                f"Expected exactly {TARGET_COUNT} records, got {n}",
            )
        return ValidationResult("V2", True, f"Exactly {TARGET_COUNT} records generated")

    def v3_no_text_overlap_with_public(self, records: list[ShouldRefuseRecord]) -> ValidationResult:
        """V3: no should-refuse prompt shares raw text with any public benchmark prompt.

        Checks SHA-256 hashes and also a 60-character sliding window to detect
        near-verbatim overlap.
        """
        # Load all public prompt texts and their hashes
        public_hashes: set[str] = set()
        public_texts: list[str] = []
        for tier_dir in ["benign", "borderline", "dual_use"]:
            tier_path = self._public_prompts_root / "v1.0" / tier_dir
            if not tier_path.exists():
                continue
            for p in tier_path.glob("*.json"):
                with p.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                text = data.get("prompt", "")
                if text:
                    public_hashes.add(hashlib.sha256(text.encode()).hexdigest())
                    public_texts.append(text)

        violations: list[str] = []
        for r in records:
            # Exact hash match
            if r.sha256_hash in public_hashes:
                violations.append(f"{r.prompt_id}: exact text match with a public benchmark prompt")
                continue
            # Sliding-window substring check (60-char fragments)
            window = 60
            text = r.prompt_text
            for i in range(0, max(1, len(text) - window + 1), window // 2):
                fragment = text[i : i + window]
                if any(fragment in pub for pub in public_texts):
                    violations.append(
                        f"{r.prompt_id}: near-verbatim fragment overlap with a public prompt "
                        f"(fragment at position {i})"
                    )
                    break

        if violations:
            return ValidationResult(
                "V3",
                False,
                f"{len(violations)} overlap(s) detected with public benchmark prompts",
                violations,
            )
        return ValidationResult("V3", True, "No text overlap with public benchmark prompts")

    def v4_no_defensive_framing(self, records: list[ShouldRefuseRecord]) -> ValidationResult:
        """V4: no should-refuse prompt contains disqualifying defensive-framing patterns.

        Checks the C4 criterion from should_refuse_criteria.yaml.
        """
        violations: list[str] = []
        for r in records:
            matched = [
                pat for pat in _DISQUALIFYING_PATTERNS if pat.lower() in r.prompt_text.lower()
            ]
            if matched:
                violations.append(f"{r.prompt_id}: disqualifying patterns found: {matched}")

        if violations:
            return ValidationResult(
                "V4",
                False,
                f"{len(violations)} prompt(s) contain disqualifying defensive-framing patterns",
                violations,
            )
        return ValidationResult("V4", True, "No defensive framing detected in any prompt")

    def v5_deterministic_ids(self, records: list[ShouldRefuseRecord]) -> ValidationResult:
        """V5: prompt IDs are deterministic and content-derived (re-hash and compare)."""
        from refusalbench.should_refuse.generator import (
            TEMPLATE_FAMILY_VERSION,
        )

        violations: list[str] = []
        for r in records:
            id_source = f"{r.anchor_id}|{r.template_id}|{TEMPLATE_FAMILY_VERSION}"
            id_hash = hashlib.sha256(id_source.encode()).hexdigest()[:8]
            subdomain_prefix = r.subdomain[:8].rstrip("_")
            expected_id = f"sr_{subdomain_prefix}_{id_hash}"

            if r.prompt_id != expected_id:
                violations.append(
                    f"prompt_id={r.prompt_id!r} does not match expected={expected_id!r}"
                )

            expected_hash = hashlib.sha256(r.prompt_text.encode("utf-8")).hexdigest()
            if r.sha256_hash != expected_hash:
                violations.append(f"{r.prompt_id}: sha256_hash mismatch (stored vs recomputed)")

        if violations:
            return ValidationResult(
                "V5", False, f"{len(violations)} ID/hash inconsistencies found", violations
            )
        return ValidationResult(
            "V5", True, "All prompt IDs and hashes are deterministic and consistent"
        )

    def v6_public_exports_have_no_prompt_text(
        self, records: list[ShouldRefuseRecord]
    ) -> ValidationResult:
        """V6: public export dicts contain only IDs/hashes — no prompt_text field."""
        violations: list[str] = []
        for r in records:
            pub = r.to_public_dict()
            if "prompt_text" in pub:
                violations.append(f"{r.prompt_id}: to_public_dict() contains 'prompt_text' key")
            # Verify the dict is JSON-serialisable without leaking text
            serialised = json.dumps(pub)
            if r.prompt_text and r.prompt_text[:40] in serialised:
                violations.append(
                    f"{r.prompt_id}: prompt_text fragment found in serialised public dict"
                )

        if violations:
            return ValidationResult(
                "V6",
                False,
                f"{len(violations)} public export(s) expose prompt_text",
                violations,
            )
        return ValidationResult(
            "V6", True, "Public exports contain IDs/hashes only — no prompt_text"
        )

    def v7_no_tracked_file_contains_prompt_text(
        self, records: list[ShouldRefuseRecord]
    ) -> ValidationResult:
        """V7: no tracked file in the repo contains any should-refuse prompt string.

        Uses ``git ls-files`` to get the full tracked-file list, then scans each
        for a 50-character leading fragment of each prompt.
        """
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            return ValidationResult("V7", False, f"Could not run git ls-files: {exc}")

        tracked_files = [self._repo_root / p for p in result.stdout.splitlines() if p.strip()]

        violations = self._scan_files_for_prompts(records, tracked_files, "tracked file")
        if violations:
            return ValidationResult(
                "V7",
                False,
                f"Should-refuse prompt text found in {len(violations)} tracked file(s)",
                violations,
            )
        return ValidationResult(
            "V7", True, f"Scanned {len(tracked_files)} tracked files — no prompt text found"
        )

    def v8_no_output_path_contains_prompt_text(
        self, records: list[ShouldRefuseRecord]
    ) -> ValidationResult:
        """V8: no output/CI artifact path contains any should-refuse prompt text.

        Scans: snapshots/, results/, qc/ and all CSV/JSON/MD files at repo root.
        """
        scan_files: list[Path] = []
        # Configured scan paths (recursive)
        for scan_path in self._scan_paths:
            if scan_path.exists():
                scan_files.extend(
                    p
                    for p in scan_path.rglob("*")
                    if p.is_file()
                    and p.suffix in {".csv", ".json", ".md", ".txt", ".yaml", ".html"}
                )
        # Root-level files
        for ext in ("*.csv", "*.json", "*.md"):
            scan_files.extend(self._repo_root.glob(ext))

        violations = self._scan_files_for_prompts(records, scan_files, "output/CI artifact")
        if violations:
            return ValidationResult(
                "V8",
                False,
                f"Should-refuse prompt text found in {len(violations)} output path(s)",
                violations,
            )
        return ValidationResult(
            "V8", True, f"Scanned {len(scan_files)} output files — no prompt text found"
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _scan_files_for_prompts(
        self,
        records: list[ShouldRefuseRecord],
        files: list[Path],
        context_label: str,
    ) -> list[str]:
        """Return a list of violation strings for any file containing a prompt fragment."""
        # Build a set of 50-char leading fragments (fast first-pass filter)
        fragments = {r.prompt_text[:50]: r.prompt_id for r in records if r.prompt_text}

        violations: list[str] = []
        for fp in files:
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for fragment, pid in fragments.items():
                if fragment in content:
                    violations.append(f"{context_label}: {fp} — contains prompt fragment for {pid}")
                    break  # one violation per file is enough

        return violations


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _default_repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parent.parent.parent.parent
