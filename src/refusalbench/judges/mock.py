"""Mock judge for tests and end-to-end demos without API keys."""

from __future__ import annotations

from refusalbench.judges.base import Judge, Judgment


class MockJudge(Judge):
    """Deterministic judge that returns a preset compliance/reason pair.

    Useful for unit tests and the 5-minute demo. The ``compliance`` and
    ``reason`` parameters are fixed at construction time.

    Parameters
    ----------
    judge_id:
        Override the default ``"mock_judge"`` id when running multiple
        instances in the same council (e.g. to simulate three distinct
        judges with different labels).
    compliance:
        compliance_level key to return for every call.
    reason:
        reason_category key to return for every call.

    Example
    -------
    >>> import asyncio
    >>> j = MockJudge(judge_id="mock_us", compliance="direct_refusal", reason="safety_policy")
    >>> result = asyncio.run(j.judge("p1", "design a binder", "I cannot help with that."))
    >>> result.compliance
    'direct_refusal'
    """

    def __init__(
        self,
        judge_id: str = "mock_judge",
        compliance: str = "compliance",
        reason: str = "other",
    ) -> None:
        self._judge_id = judge_id
        self._compliance = compliance
        self._reason = reason

    @property
    def judge_id(self) -> str:
        return self._judge_id

    async def judge(
        self,
        prompt_id: str,
        prompt_text: str,
        response_text: str,
    ) -> Judgment:
        """Return the preset compliance/reason pair immediately."""
        raw = f"COMPLIANCE: {self._compliance}\nREASON: {self._reason}"
        return Judgment(
            judge_id=self._judge_id,
            prompt_id=prompt_id,
            compliance=self._compliance,
            reason=self._reason,
            raw_output=raw,
            parse_failed=False,
        )
