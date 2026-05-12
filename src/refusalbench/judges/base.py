"""Abstract judge base class and Judgment dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Judgment:
    """One judge's classification of a single (prompt, response) pair.

    Attributes
    ----------
    judge_id : str
        Identifier matching the council config entry.
    prompt_id : str
        The prompt being judged.
    compliance : str
        One of the ``compliance_levels[].key`` values from benchmark/rubric.json.
    reason : str
        One of the ``reason_categories[].key`` values from benchmark/rubric.json.
    raw_output : str
        Verbatim model output before parsing. Kept for audit.
    parse_failed : bool
        True when the model returned un-parseable output; compliance and
        reason will be "non_responsive" and "other" in that case.

    Example
    -------
    >>> j = Judgment(
    ...     judge_id="llama_guard_4",
    ...     prompt_id="binder_001_benign",
    ...     compliance="direct_refusal",
    ...     reason="biosecurity_concern",
    ...     raw_output="LABEL: direct_refusal\\nREASON: biosecurity_concern",
    ...     parse_failed=False,
    ... )
    >>> j.compliance
    'direct_refusal'
    """

    judge_id: str
    prompt_id: str
    compliance: str
    reason: str
    raw_output: str
    parse_failed: bool = False


class JudgmentError(RuntimeError):
    """Raised when a judge fails after all retries."""


class Judge(ABC):
    """Abstract base class for all council judges.

    Subclasses implement :meth:`judge` which calls the underlying model
    and parses the result into a :class:`Judgment`.

    Example
    -------
    >>> class MyJudge(Judge):
    ...     @property
    ...     def judge_id(self) -> str:
    ...         return "my_judge"
    ...     async def judge(self, prompt_id, prompt_text, response_text):
    ...         return Judgment(
    ...             judge_id=self.judge_id,
    ...             prompt_id=prompt_id,
    ...             compliance="compliance",
    ...             reason="other",
    ...             raw_output="",
    ...         )
    """

    @property
    @abstractmethod
    def judge_id(self) -> str:
        """Unique identifier matching council config."""

    @abstractmethod
    async def judge(
        self,
        prompt_id: str,
        prompt_text: str,
        response_text: str,
    ) -> Judgment:
        """Classify a (prompt, response) pair.

        Must return a :class:`Judgment` even on soft failures; set
        ``parse_failed=True`` rather than raising when output is
        malformed.

        Parameters
        ----------
        prompt_id:
            The prompt identifier for correlation.
        prompt_text:
            The verbatim prompt shown to the evaluated model.
        response_text:
            The model response to classify.

        Raises
        ------
        JudgmentError
            Only on hard failures (network errors after retries, etc.).
        """
