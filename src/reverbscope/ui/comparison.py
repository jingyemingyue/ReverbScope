"""The comparison of the current entry with the baseline, as the compare view
and the inspector show it.

``reverbscope compare`` computes it from two session folders; here the two
results are already open in the workspace model, so the same functions run
on them directly. A comparison is cached per entry pair and gain setting:
the compare view, its difference chart and the inspector's verdict line all
read one computation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from reverbscope.core.compare import compare
from reverbscope.errors import ReverbScopeError
from reverbscope.interpretation import interpret_comparison
from reverbscope.interpretation.interpreter import Finding
from reverbscope.interpretation.verdicts import ComparisonVerdict, judge_comparison
from reverbscope.models.comparison import CompareSettings, ComparisonResult
from reverbscope.ui.workspace import Entry, WorkspaceModel


@dataclass(frozen=True)
class EntryComparison:
    """The current entry (candidate) against the baseline."""

    baseline: Entry
    candidate: Entry
    comparison: ComparisonResult
    findings: list[Finding]
    profile: str
    verdict: ComparisonVerdict


def compare_entries(
    model: WorkspaceModel, baseline: Entry, candidate: Entry, *, same_gain: bool
) -> EntryComparison:
    """``candidate`` against ``baseline``, computed once per pair and setting.

    Raises :class:`ReverbScopeError` when the two results cannot be compared
    at all (its message is English; show it through ``localize``).
    """
    if baseline.result is None or candidate.result is None:
        raise ValueError("both entries must be loaded")
    name = ("comparison", baseline.key, same_gain)
    cached = model.cache_get(candidate.key, name)
    if isinstance(cached, EntryComparison) and cached.baseline is baseline:
        return cached
    comparison = replace(
        compare(
            baseline.result,
            candidate.result,
            settings=CompareSettings(same_input_gain=same_gain),
        ),
        baseline_session=str(baseline.directory) if baseline.directory else baseline.key,
        candidate_session=str(candidate.directory) if candidate.directory else candidate.key,
    )
    # As `reverbscope compare`: the candidate's profile, generic when it fails.
    profile = candidate.profile or "generic"
    try:
        findings = interpret_comparison(comparison, profile)
    except ReverbScopeError:
        profile = "generic"
        findings = interpret_comparison(comparison, profile)
    verdict = judge_comparison(
        comparison, profile, baseline=baseline.result, candidate=candidate.result
    )
    value = EntryComparison(baseline, candidate, comparison, findings, profile, verdict)
    model.cache_put(candidate.key, name, value)
    return value


def current_comparison(model: WorkspaceModel, *, same_gain: bool) -> EntryComparison | None:
    """The current entry against the baseline, or ``None`` when there is no pair."""
    baseline = model.baseline()
    candidate = model.current()
    if (
        baseline is None
        or candidate is None
        or baseline.key == candidate.key
        or baseline.result is None
        or candidate.result is None
    ):
        return None
    return compare_entries(model, baseline, candidate, same_gain=same_gain)
