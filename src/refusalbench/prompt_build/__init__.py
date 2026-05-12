"""Deterministic prompt construction pipeline (Layer A).

This subpackage contains all benchmark-defining logic. No LLM calls here.
"""

from refusalbench.prompt_build.catalogue import CandidateRecord, RiskAnnotation
from refusalbench.prompt_build.rendering import PromptRenderer
from refusalbench.prompt_build.tier_rules import TierAssignment, assign_tier
from refusalbench.prompt_build.validators import HardValidator, ValidationError

__all__ = [
    "CandidateRecord",
    "HardValidator",
    "PromptRenderer",
    "RiskAnnotation",
    "TierAssignment",
    "ValidationError",
    "assign_tier",
]
