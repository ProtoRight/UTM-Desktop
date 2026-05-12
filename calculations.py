"""Mechanical property calculations for 3-point bend and tensile tests.

Data preprocessing
------------------
trim_errant_start   — removes stale pre-test displacement readings; the first
                      RUNNING packet arrives before the Arduino zeroes the DRO,
                      so displacement may be positive or negative from prior
                      movement.  Looks for the first near-zero point in the
                      opening window and discards everything before it.
offset_to_zero      — subtracts the first point's displacement so x starts at 0

Modulus calculation
-------------------
Chord modulus between two standard strain points (ISO 178 / ASTM D790).
Default bounds: ε₁ = 0.05 %, ε₂ = 0.25 % (ISO 178).
ASTM D790 uses 0.1 % / 0.3 % — adjust CHORD_EPS_1 / CHORD_EPS_2 if needed.
Onset is detected as the first point where load ≥ 1 % of peak load.
Strain is measured from onset displacement; upper bound falls back to
maximum available strain when fracture occurs before ε₂.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

G = 9.80665  # m/s²


# ---------------------------------------------------------------------------
# Specimen geometry
# ---------------------------------------------------------------------------

@dataclass
class SpecimenData:
    material: str = ""
    sample_id: str = ""
    test_type: str = "3PT"
    geometry: str = "rectangular"

    width_mm: float     = 0.0
    thickness_mm: float = 0.0
    diameter_mm: float  = 0.0
    outer_dia_mm: float = 0.0
    inner_dia_mm: float = 0.0
    span_mm: float      = 0.0
    gauge_length_mm: float = 0.0

    def cross_section_area_mm2(self) -> float:
        if self.geometry == "rectangular":
            return self.width_mm * self.thickness_mm
        if self.geometry == "circular":
            return math.pi * (self.diameter_mm / 2) ** 2
        if self.geometry == "hollow":
            return math.pi * (
                (self.outer_dia_mm / 2) ** 2 - (self.inner_dia_mm / 2) ** 2
            )
        return 0.0

    def second_moment_of_area_mm4(self) -> float:
        if self.geometry == "rectangular":
            return (self.width_mm * self.thickness_mm ** 3) / 12.0
        if self.geometry == "circular":
            return math.pi * self.diameter_mm ** 4 / 64.0
        if self.geometry == "hollow":
            return math.pi * (self.outer_dia_mm ** 4 - self.inner_dia_mm ** 4) / 64.0
        return 0.0

    def outer_fibre_distance_mm(self) -> float:
        if self.geometry == "rectangular":
            return self.thickness_mm / 2.0
        if self.geometry == "circular":
            return self.diameter_mm / 2.0
        if self.geometry == "hollow":
            return self.outer_dia_mm / 2.0
        return 0.0

    def is_valid_for_test(self) -> tuple[bool, str]:
        if self.geometry == "rectangular":
            if self.width_mm <= 0 or self.thickness_mm <= 0:
                return False, "Width and thickness must be > 0"
        elif self.geometry == "circular":
            if self.diameter_mm <= 0:
                return False, "Diameter must be > 0"
        elif self.geometry == "hollow":
            if self.outer_dia_mm <= 0 or self.inner_dia_mm <= 0:
                return False, "Outer and inner diameters must be > 0"
            if self.inner_dia_mm >= self.outer_dia_mm:
                return False, "Inner diameter must be less than outer diameter"
        if self.test_type == "3PT" and self.span_mm <= 0:
            return False, "Span length must be > 0"
        if self.test_type == "TENSILE" and self.gauge_length_mm <= 0:
            return False, "Gauge length must be > 0"
        return True, ""


# ---------------------------------------------------------------------------
# Results containers
# ---------------------------------------------------------------------------

@dataclass
class BendResults:
    peak_load_kg: float         = 0.0
    peak_load_N: float          = 0.0
    peak_displacement_mm: float = 0.0
    flexural_stress_MPa: Optional[float]  = None
    flexural_strain_peak: Optional[float] = None
    flexural_modulus_GPa: Optional[float] = None
    linear_region_onset_mm: Optional[float] = None
    linear_region_onset_load_kg: Optional[float] = None
    linear_region_end_mm: Optional[float] = None
    linear_region_slope_kg_per_mm: Optional[float] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class TensileResults:
    peak_load_kg: float          = 0.0
    peak_load_N: float           = 0.0
    peak_displacement_mm: float  = 0.0
    cross_section_area_mm2: Optional[float] = None
    uts_MPa: Optional[float]            = None
    strain_at_peak: Optional[float]     = None
    youngs_modulus_GPa: Optional[float] = None
    yield_strength_MPa: Optional[float] = None
    linear_region_onset_mm: Optional[float] = None
    linear_region_onset_load_kg: Optional[float] = None
    linear_region_end_mm: Optional[float] = None
    linear_region_slope_kg_per_mm: Optional[float] = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Data preprocessing
# ---------------------------------------------------------------------------

def trim_errant_start(
    points: list[tuple[float, float]],
    window: int = 15,
    tolerance_mm: float = 0.15,
) -> list[tuple[float, float]]:
    """Remove initial displacement outliers caused by a stale DRO reading.

    The Arduino zeros the DRO when a test starts, but the first RUNNING packet
    arrives before that zero command takes effect, so it carries the pre-test
    displacement (positive or negative).

    Strategy:
    1. If the first point is already near zero, nothing to trim.
    2. Find the first point within the opening `window` whose displacement is
       near zero — that is where the Arduino-zeroed data begins.  Discard
       everything before it.
    3. Fallback (positive stale value with no near-zero point): find the
       minimum displacement in the window and discard points before it.
    """
    if len(points) < 3:
        return points

    check_n = min(window, len(points))
    early_disps = [p[0] for p in points[:check_n]]

    # Already at zero — nothing to do
    if abs(early_disps[0]) <= tolerance_mm:
        return points

    # Primary: find first point near zero (post-Arduino-zero reading)
    zero_idx = next(
        (i for i, d in enumerate(early_disps) if abs(d) <= tolerance_mm),
        None,
    )
    if zero_idx is not None:
        return points[zero_idx:]

    # Fallback: positive stale value, no near-zero found — trim to minimum
    min_disp = min(early_disps)
    if early_disps[0] <= min_disp + tolerance_mm:
        return points
    start_idx = next(
        (i for i, d in enumerate(early_disps) if d <= min_disp + tolerance_mm),
        0,
    )
    return points[start_idx:]


def offset_to_zero(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Shift all displacement values so the first point starts at 0."""
    if not points:
        return points
    d0 = points[0][0]
    if abs(d0) < 1e-6:
        return points
    return [(d - d0, f) for d, f in points]


def preprocess(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Full preprocessing pipeline: trim errant start → offset to zero."""
    return offset_to_zero(trim_errant_start(points))


# ---------------------------------------------------------------------------
# Chord modulus (ISO 178 / ASTM D790)
# ---------------------------------------------------------------------------

# Strain bounds measured from contact onset.
# ISO 178 uses 0.05 % – 0.25 %; ASTM D790 uses 0.10 % – 0.30 %.
CHORD_EPS_1: float = 0.0005   # 0.05 %
CHORD_EPS_2: float = 0.0025   # 0.25 %


def _find_onset_idx(load: np.ndarray, threshold: float = 0.01) -> int:
    """Index of first point where load ≥ threshold × peak load."""
    peak = float(np.max(load))
    if peak <= 0:
        return 0
    thresh = peak * threshold
    for i in range(len(load)):
        if load[i] >= thresh:
            return i
    return 0


def _chord_modulus_mpa(
    delta_strain: np.ndarray,
    stress_mpa: np.ndarray,
    eps1: float,
    eps2: float,
) -> tuple[Optional[float], float, str]:
    """Chord modulus E = Δσ/Δε between eps1 and eps2.

    Both eps1 and eps2 are strain measured from the contact onset.
    Returns (E_MPa or None, actual_eps2_used, note).
    Falls back to max available strain when fracture occurs before eps2.
    """
    if len(delta_strain) == 0:
        return None, eps2, "No data — modulus not calculated."
    max_eps = float(delta_strain[-1])
    if max_eps < eps1:
        return None, eps2, (
            f"Fracture before chord lower bound ε = {eps1 * 100:.2f}% "
            "— modulus not calculated."
        )
    actual_eps2 = min(eps2, max_eps)
    sigma1 = float(np.interp(eps1,        delta_strain, stress_mpa))
    sigma2 = float(np.interp(actual_eps2, delta_strain, stress_mpa))
    denom  = actual_eps2 - eps1
    if denom < 1e-10:
        return None, actual_eps2, "Chord range too narrow — modulus not calculated."
    E = (sigma2 - sigma1) / denom
    if actual_eps2 < eps2 * 0.999:
        note = (
            f"Chord modulus ε {eps1 * 100:.2f}%→{actual_eps2 * 100:.3f}% "
            f"(fracture before standard upper bound {eps2 * 100:.2f}%)."
        )
    else:
        note = (
            f"Chord modulus ε {eps1 * 100:.2f}%→{actual_eps2 * 100:.2f}% "
            "(ISO 178 / ASTM D790)."
        )
    return E, actual_eps2, note


# ---------------------------------------------------------------------------
# 0.2 % offset yield strength
# ---------------------------------------------------------------------------

def _yield_02_offset(
    strain: np.ndarray,
    stress: np.ndarray,
    E_MPa: float,
    onset_strain: float = 0.0,
) -> Optional[float]:
    """0.2 % offset yield strength.  Returns None if no crossing is found.

    The offset line is σ = E·(ε − onset_strain − 0.002), i.e. 0.2 % to the
    right of the contact onset rather than from the machine zero.
    """
    offset_stress = E_MPa * (strain - onset_strain - 0.002)
    diff = stress - offset_stress
    for i in range(len(diff) - 1):
        if diff[i] * diff[i + 1] <= 0 and i > 0:
            t = -diff[i] / (diff[i + 1] - diff[i] + 1e-12)
            return float(stress[i] + t * (stress[i + 1] - stress[i]))
    return None


# ---------------------------------------------------------------------------
# Main calculation functions
# ---------------------------------------------------------------------------

def calculate_bend(
    disp_mm: list[float],
    load_kg: list[float],
    specimen: SpecimenData,
) -> BendResults:
    res = BendResults()
    if not disp_mm or not load_kg:
        res.notes.append("No data points.")
        return res

    disp = np.array(disp_mm, dtype=float)
    load = np.array(load_kg, dtype=float)

    res.peak_load_kg        = float(np.max(load))
    res.peak_load_N         = res.peak_load_kg * G
    peak_idx                = int(np.argmax(load))
    res.peak_displacement_mm = float(disp[peak_idx])

    ok, reason = specimen.is_valid_for_test()
    if not ok:
        res.notes.append(f"Cannot calculate properties: {reason}")
        return res

    L = specimen.span_mm
    I = specimen.second_moment_of_area_mm4()
    c = specimen.outer_fibre_distance_mm()

    if I <= 0 or c <= 0:
        res.notes.append("Invalid cross-section (I or c = 0).")
        return res

    # Flexural stress at peak: σ = M·c/I, M = F·L/4
    res.flexural_stress_MPa = (res.peak_load_N * L / 4.0) * c / I

    # Flexural strain at peak: ε = 12·δ·c / L²
    res.flexural_strain_peak = 12.0 * res.peak_displacement_mm * c / (L ** 2)

    # Flexural modulus — chord method (ISO 178 / ASTM D790)
    onset_idx  = _find_onset_idx(load)
    onset_disp = float(disp[onset_idx])
    onset_load = float(load[onset_idx])
    post_disp  = disp[onset_idx:]
    post_load  = load[onset_idx:]
    # Flexural strain and stress from onset onwards
    delta_strain = 12.0 * (post_disp - onset_disp) * c / L ** 2
    flex_stress  = post_load * G * L * c / (4.0 * I)   # MPa

    E_MPa, used_eps2, mod_note = _chord_modulus_mpa(
        delta_strain, flex_stress, CHORD_EPS_1, CHORD_EPS_2
    )
    res.notes.append(mod_note)
    if E_MPa is not None and E_MPa > 0:
        res.flexural_modulus_GPa          = E_MPa / 1000.0
        res.linear_region_onset_mm        = onset_disp
        res.linear_region_onset_load_kg   = onset_load
        chord_end = onset_disp + used_eps2 * L ** 2 / (12.0 * c)
        res.linear_region_end_mm          = min(chord_end, res.peak_displacement_mm)
        # dF/dδ [kg/mm] = E_f [N/mm²] × 48I [mm⁴] / (G [N/kg] × L³ [mm³])
        res.linear_region_slope_kg_per_mm = E_MPa * 48.0 * I / (G * L ** 3)

    return res


def calculate_tensile(
    disp_mm: list[float],
    load_kg: list[float],
    specimen: SpecimenData,
) -> TensileResults:
    res = TensileResults()
    if not disp_mm or not load_kg:
        res.notes.append("No data points.")
        return res

    disp = np.array(disp_mm, dtype=float)
    load = np.array(load_kg, dtype=float)

    res.peak_load_kg         = float(np.max(load))
    res.peak_load_N          = res.peak_load_kg * G
    peak_idx                 = int(np.argmax(load))
    res.peak_displacement_mm = float(disp[peak_idx])

    ok, reason = specimen.is_valid_for_test()
    if not ok:
        res.notes.append(f"Cannot calculate properties: {reason}")
        return res

    A  = specimen.cross_section_area_mm2()
    L0 = specimen.gauge_length_mm

    if A <= 0:
        res.notes.append("Invalid cross-section area (A = 0).")
        return res

    res.cross_section_area_mm2 = A
    res.uts_MPa                = res.peak_load_N / A
    res.strain_at_peak         = res.peak_displacement_mm / L0

    stress = load * G / A    # MPa at each point
    strain = disp / L0       # engineering strain at each point

    # Young's modulus — chord method (ISO 527 / ASTM E111)
    onset_idx  = _find_onset_idx(load)
    onset_disp = float(disp[onset_idx])
    onset_load = float(load[onset_idx])
    post_disp  = disp[onset_idx:]
    post_load  = load[onset_idx:]
    delta_strain_post = (post_disp - onset_disp) / L0
    eng_stress_post   = post_load * G / A              # MPa

    E_MPa, used_eps2, mod_note = _chord_modulus_mpa(
        delta_strain_post, eng_stress_post, CHORD_EPS_1, CHORD_EPS_2
    )
    res.notes.append(mod_note)
    if E_MPa is not None and E_MPa > 0:
        res.youngs_modulus_GPa             = E_MPa / 1000.0
        res.linear_region_onset_mm         = onset_disp
        res.linear_region_onset_load_kg    = onset_load
        chord_end                          = onset_disp + used_eps2 * L0
        res.linear_region_end_mm           = min(chord_end, res.peak_displacement_mm)
        res.linear_region_slope_kg_per_mm  = E_MPa * A / (G * L0)

        # 0.2 % offset yield strength (offset from contact onset)
        onset_strain = onset_disp / L0
        res.yield_strength_MPa = _yield_02_offset(strain, stress, E_MPa, onset_strain)
        if res.yield_strength_MPa is not None:
            res.notes.append("Yield strength via 0.2 % offset method.")
        else:
            res.notes.append("0.2 % offset yield point not found in data.")

    return res
