from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class TestData:
    """Holds all data points captured during a single test run."""

    points: List[Tuple[float, float]] = field(default_factory=list)
    peak_load: float = 0.0
    peak_displacement: float = 0.0
    completion_reason: Optional[str] = None  # "travel" | "load" | "drop" | "manual" | "arduino"

    # --- mutation ---------------------------------------------------------

    def add_point(self, displacement: float, load: float) -> None:
        self.points.append((displacement, load))
        if load > self.peak_load:
            self.peak_load = load
            self.peak_displacement = displacement

    def clear(self) -> None:
        self.points.clear()
        self.peak_load = 0.0
        self.peak_displacement = 0.0
        self.completion_reason = None

    # --- completion checks ------------------------------------------------

    def check_travel_limit(self, limit_mm: float) -> bool:
        if not self.points:
            return False
        return self.points[-1][0] >= limit_mm

    def check_load_limit(self, limit_kg: float) -> bool:
        if not self.points:
            return False
        return self.points[-1][1] >= limit_kg

    def check_load_drop(self, threshold_pct: float, window: int) -> bool:
        """True if load has dropped >= threshold_pct% from the rolling-window peak.

        Requires peak_load > 1 kg to avoid triggering before load has built up.
        """
        if len(self.points) < window or self.peak_load < 1.0:
            return False
        recent_loads = [p[1] for p in self.points[-window:]]
        window_peak = max(recent_loads)
        current_load = self.points[-1][1]
        if window_peak <= 0:
            return False
        drop_pct = (window_peak - current_load) / window_peak * 100.0
        return drop_pct >= threshold_pct

    # --- convenience views -----------------------------------------------

    def displacements(self) -> List[float]:
        return [p[0] for p in self.points]

    def loads(self) -> List[float]:
        return [p[1] for p in self.points]

    def is_empty(self) -> bool:
        return len(self.points) == 0
