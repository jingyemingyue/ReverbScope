"""Recommendation planner. Beginners see one next action, not a room score."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from reverbscope.experimental.guided.findings import Priority, StructuredFinding


class Expertise(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"


_PRIORITY_ORDER = {
    Priority.P0: 0,
    Priority.P1: 1,
    Priority.P2: 2,
    Priority.P3: 3,
}


@dataclass(frozen=True)
class RecommendationPlan:
    ordered: tuple[StructuredFinding, ...]
    next_best: StructuredFinding | None
    visible: tuple[StructuredFinding, ...]
    expertise: Expertise

    def to_dict(self) -> dict[str, object]:
        return {
            "expertise": self.expertise.value,
            "next_best_action": None if self.next_best is None else self.next_best.finding_id,
            "visible": [item.finding_id for item in self.visible],
            "ordered": [item.finding_id for item in self.ordered],
        }


def plan_recommendations(
    findings: tuple[StructuredFinding, ...] | list[StructuredFinding],
    expertise: Expertise | str = Expertise.BEGINNER,
) -> RecommendationPlan:
    level = expertise if isinstance(expertise, Expertise) else Expertise(expertise)
    ordered = tuple(sorted(findings, key=lambda item: _PRIORITY_ORDER[item.priority]))
    nxt = ordered[0] if ordered else None
    visible: tuple[StructuredFinding, ...]
    if level is Expertise.BEGINNER:
        visible = () if nxt is None else (nxt,)
    elif level is Expertise.INTERMEDIATE:
        visible = ordered[:3]
    else:
        visible = ordered
    return RecommendationPlan(ordered=ordered, next_best=nxt, visible=visible, expertise=level)
