"""RefusalBench — process-aware refusal benchmark for LLMs.

Public API surface:

    from refusalbench import (
        Prompt, Tier, Subdomain,
        load_prompts, load_paired_sets,
        Judgment, AggregatedJudgment,
        categorize, aggregate,
        compute_refusal_rate, inter_judge_agreement, bootstrap_ci,
    )

Real model and judge wiring lives behind the optional `[providers]`
extra; everything in the default install runs end-to-end on mock
providers and mock judges, which is what the test suite uses.
"""

from refusalbench.council import (
    AggregatedJudgment,
    aggregate,
    categorize,
)
from refusalbench.judges.base import Judge, Judgment
from refusalbench.prompts import (
    FrozenPromptSetError,
    Prompt,
    Subdomain,
    Tier,
    load_paired_sets,
    load_prompts,
)
from refusalbench.score import (
    bootstrap_ci,
    compute_refusal_rate,
    inter_judge_agreement,
    tier_comparison,
)

__version__ = "0.1.0"

__all__ = [
    "AggregatedJudgment",
    "FrozenPromptSetError",
    "Judge",
    "Judgment",
    "Prompt",
    "Subdomain",
    "Tier",
    "aggregate",
    "bootstrap_ci",
    "categorize",
    "compute_refusal_rate",
    "inter_judge_agreement",
    "load_paired_sets",
    "load_prompts",
    "tier_comparison",
]
