"""Optional LLM-council QC layer (Layer B).

IMPORTANT: This module is NOT part of benchmark construction.
It provides audit metadata, flagging, and disagreement analysis only.
Council outputs never automatically mutate the benchmark dataset.

Usage:
    python scripts/generate_prompts.py --run-qc-council

The benchmark JSON is identical with or without QC.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class QCError(RuntimeError):
    """Raised when QC council encounters an unrecoverable error."""


@dataclass
class QCJudgment:
    """One judge's responses to the five QC questions for one prompt.

    Parameters
    ----------
    judge_id:
        Identifier matching the panel entry in qc_council_config.json.
    prompt_id:
        The prompt being evaluated.
    q1_naturalness:
        "yes" / "borderline" / "no"
    q2_tier_leakage:
        "low" / "medium" / "high"
    q3_template_artifact:
        "low" / "medium" / "high"
    q4_scientific_plausibility:
        "yes" / "uncertain" / "no"
    q5_sensitivity_mismatch:
        "aligned" / "possibly_mismatched" / "mismatched"
    raw_output:
        The unparsed model response.
    parse_failed:
        True if the response could not be parsed.
    """

    judge_id: str
    prompt_id: str
    q1_naturalness: str = "unknown"
    q2_tier_leakage: str = "unknown"
    q3_template_artifact: str = "unknown"
    q4_scientific_plausibility: str = "unknown"
    q5_sensitivity_mismatch: str = "unknown"
    raw_output: str = ""
    parse_failed: bool = False
    rationale: dict[str, str] = field(default_factory=dict)


@dataclass
class AggregatedQCScore:
    """Aggregated QC scores for one prompt across all panel judges.

    Parameters
    ----------
    prompt_id:
        The evaluated prompt.
    modal_naturalness:
        Modal answer for Q1.
    modal_tier_leakage:
        Modal answer for Q2.
    modal_template_artifact:
        Modal answer for Q3.
    modal_plausibility:
        Modal answer for Q4.
    modal_sensitivity_mismatch:
        Modal answer for Q5.
    flagged:
        True if any flagging rule is triggered.
    flag_reasons:
        List of triggered flag rule names.
    disagreement_score:
        Fraction of question pairs where judges disagreed.
    """

    prompt_id: str
    modal_naturalness: str
    modal_tier_leakage: str
    modal_template_artifact: str
    modal_plausibility: str
    modal_sensitivity_mismatch: str
    flagged: bool
    flag_reasons: list[str]
    disagreement_score: float
    judge_count: int


def aggregate_qc_judgments(
    judgments: list[QCJudgment],
    flagging_rules: dict[str, object],
) -> AggregatedQCScore:
    """Aggregate per-judge QC judgments into one score.

    Parameters
    ----------
    judgments:
        All judges' judgments for one prompt.
    flagging_rules:
        The ``flagging_rules`` dict from qc_council_config.json.

    Returns
    -------
    AggregatedQCScore

    Examples
    --------
    >>> j1 = QCJudgment("j1", "p1", q1_naturalness="yes", q2_tier_leakage="low",
    ...                  q3_template_artifact="low", q4_scientific_plausibility="yes",
    ...                  q5_sensitivity_mismatch="aligned")
    >>> j2 = QCJudgment("j2", "p1", q1_naturalness="yes", q2_tier_leakage="low",
    ...                  q3_template_artifact="low", q4_scientific_plausibility="yes",
    ...                  q5_sensitivity_mismatch="aligned")
    >>> result = aggregate_qc_judgments([j1, j2], {})
    >>> result.flagged
    False
    """
    if not judgments:
        raise QCError("No judgments to aggregate")

    prompt_id = judgments[0].prompt_id
    questions = [
        "q1_naturalness",
        "q2_tier_leakage",
        "q3_template_artifact",
        "q4_scientific_plausibility",
        "q5_sensitivity_mismatch",
    ]

    def modal(attr: str) -> str:
        values: list[str] = [str(getattr(j, attr)) for j in judgments if not j.parse_failed]
        if not values:
            return "unknown"
        return str(max(set(values), key=values.count))

    modal_answers = {q: modal(q) for q in questions}

    # Disagreement score
    total_pairs = 0
    disagreeing_pairs = 0
    for q in questions:
        vals = [getattr(j, q) for j in judgments if not j.parse_failed]
        for i in range(len(vals)):
            for v2 in vals[i + 1 :]:
                total_pairs += 1
                if vals[i] != v2:
                    disagreeing_pairs += 1
    disagreement_score = disagreeing_pairs / total_pairs if total_pairs > 0 else 0.0

    # Flagging
    flag_reasons: list[str] = []
    n = len(judgments)

    def majority(attr: str, value: str) -> bool:
        count = sum(1 for j in judgments if not j.parse_failed and getattr(j, attr) == value)
        return count > n / 2

    if flagging_rules.get("flag_if_majority_naturalness_no") and majority("q1_naturalness", "no"):
        flag_reasons.append("majority_naturalness_no")
    if flagging_rules.get("flag_if_majority_tier_leakage_high") and majority(
        "q2_tier_leakage", "high"
    ):
        flag_reasons.append("majority_tier_leakage_high")
    if flagging_rules.get("flag_if_majority_template_artifact_high") and majority(
        "q3_template_artifact", "high"
    ):
        flag_reasons.append("majority_template_artifact_high")
    if flagging_rules.get("flag_if_majority_plausibility_no") and majority(
        "q4_scientific_plausibility", "no"
    ):
        flag_reasons.append("majority_plausibility_no")
    if flagging_rules.get("flag_if_majority_sensitivity_mismatched") and majority(
        "q5_sensitivity_mismatch", "mismatched"
    ):
        flag_reasons.append("majority_sensitivity_mismatched")
    threshold = float(flagging_rules.get("flag_if_disagreement_exceeds", 0.7))  # type: ignore[arg-type]
    if disagreement_score > threshold:
        flag_reasons.append(f"disagreement_score_{disagreement_score:.2f}")

    return AggregatedQCScore(
        prompt_id=prompt_id,
        modal_naturalness=modal_answers["q1_naturalness"],
        modal_tier_leakage=modal_answers["q2_tier_leakage"],
        modal_template_artifact=modal_answers["q3_template_artifact"],
        modal_plausibility=modal_answers["q4_scientific_plausibility"],
        modal_sensitivity_mismatch=modal_answers["q5_sensitivity_mismatch"],
        flagged=len(flag_reasons) > 0,
        flag_reasons=flag_reasons,
        disagreement_score=disagreement_score,
        judge_count=len(judgments),
    )


def parse_qc_response(raw: str, judge_id: str, prompt_id: str) -> QCJudgment:
    """Parse a structured QC response from a judge model.

    Expected format (JSON):
    {
      "q1_naturalness": "yes|borderline|no",
      "q2_tier_leakage": "low|medium|high",
      "q3_template_artifact": "low|medium|high",
      "q4_scientific_plausibility": "yes|uncertain|no",
      "q5_sensitivity_mismatch": "aligned|possibly_mismatched|mismatched",
      "rationale": { ... }
    }

    Parameters
    ----------
    raw:
        The raw model output string.
    judge_id:
        The judge that produced this output.
    prompt_id:
        The prompt being evaluated.

    Returns
    -------
    QCJudgment
        With ``parse_failed=True`` if parsing fails.

    Examples
    --------
    >>> j = parse_qc_response(
    ...     '{"q1_naturalness": "yes", "q2_tier_leakage": "low", '
    ...     '"q3_template_artifact": "low", "q4_scientific_plausibility": "yes", '
    ...     '"q5_sensitivity_mismatch": "aligned"}',
    ...     "judge_1", "prompt_1"
    ... )
    >>> j.q1_naturalness
    'yes'
    >>> j.parse_failed
    False
    """
    import re as _re

    text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=_re.MULTILINE)
    try:
        data = json.loads(text)
        return QCJudgment(
            judge_id=judge_id,
            prompt_id=prompt_id,
            q1_naturalness=str(data.get("q1_naturalness", "unknown")),
            q2_tier_leakage=str(data.get("q2_tier_leakage", "unknown")),
            q3_template_artifact=str(data.get("q3_template_artifact", "unknown")),
            q4_scientific_plausibility=str(data.get("q4_scientific_plausibility", "unknown")),
            q5_sensitivity_mismatch=str(data.get("q5_sensitivity_mismatch", "unknown")),
            raw_output=raw,
            parse_failed=False,
            rationale=dict(data.get("rationale", {})),
        )
    except (json.JSONDecodeError, AttributeError):
        return QCJudgment(
            judge_id=judge_id,
            prompt_id=prompt_id,
            raw_output=raw,
            parse_failed=True,
        )


def write_qc_outputs(
    scores: list[AggregatedQCScore],
    raw_judgments: list[QCJudgment],
    output_dir: Path,
) -> None:
    """Write all QC output files to the output directory.

    Parameters
    ----------
    scores:
        Aggregated scores, one per prompt.
    raw_judgments:
        All raw judgments from all judges.
    output_dir:
        Directory to write QC output files (e.g. ``qc/v1.0/``).
    """
    import csv

    output_dir.mkdir(parents=True, exist_ok=True)

    # raw_judgments.jsonl
    with (output_dir / "raw_judgments.jsonl").open("w") as f:
        for j in raw_judgments:
            f.write(json.dumps(j.__dict__) + "\n")

    # aggregated_scores.csv
    score_fields = [
        "prompt_id",
        "modal_naturalness",
        "modal_tier_leakage",
        "modal_template_artifact",
        "modal_plausibility",
        "modal_sensitivity_mismatch",
        "flagged",
        "flag_reasons",
        "disagreement_score",
        "judge_count",
    ]
    with (output_dir / "aggregated_scores.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=score_fields)
        writer.writeheader()
        for s in scores:
            row = s.__dict__.copy()
            row["flag_reasons"] = "|".join(s.flag_reasons)
            writer.writerow(row)

    # flagged_prompts.csv
    flagged = [s for s in scores if s.flagged]
    with (output_dir / "flagged_prompts.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=score_fields)
        writer.writeheader()
        for s in flagged:
            row = s.__dict__.copy()
            row["flag_reasons"] = "|".join(s.flag_reasons)
            writer.writerow(row)

    # disagreement_summary.csv
    with (output_dir / "disagreement_summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["prompt_id", "disagreement_score", "flagged"])
        writer.writeheader()
        for s in sorted(scores, key=lambda x: -x.disagreement_score):
            writer.writerow(
                {
                    "prompt_id": s.prompt_id,
                    "disagreement_score": f"{s.disagreement_score:.3f}",
                    "flagged": s.flagged,
                }
            )

    # qc_readme.md
    with (output_dir / "qc_readme.md").open("w") as f:
        f.write("# QC Council Outputs\n\n")
        f.write("These files are auxiliary audit artifacts. They do not define the benchmark.\n\n")
        f.write(f"- Total prompts evaluated: {len(scores)}\n")
        f.write(f"- Flagged prompts: {len(flagged)}\n")
        f.write(f"- Total raw judgments: {len(raw_judgments)}\n")
