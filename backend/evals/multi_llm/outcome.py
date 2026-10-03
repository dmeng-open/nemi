from dataclasses import dataclass, field

from app.agents.itinerary.artifacts import Itinerary, ItineraryConstraints


@dataclass
class Outcome:
    """One case after the deterministic steps and, when present, the live judgments."""

    itinerary: Itinerary | None
    constraints: ItineraryConstraints
    illegal_ids: frozenset[str]
    chosen_ids: frozenset[str] = field(default_factory=frozenset)
    selection_errors: tuple[str, ...] = ()
    meal_dietary: str | None = None
    write_count: int = 0
    task_status: dict[str, str] = field(default_factory=dict)
    reopened_task_ids: tuple[str, ...] = ()
    second_wave_new_ids: tuple[str, ...] = ()
    stopped: bool = True
    replan_attempted: bool = False
    dataset_version: str = ""
