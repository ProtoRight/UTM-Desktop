"""Mechanical property calculations for 3-point bend and tensile tests."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

G = 9.81  # m/s² — kg-force to Newtons


# ---------------------------------------------------------------------------
# Specimen geometry
# ---------------------------------------------------------------------------

@dataclass
class SpecimenData:
    material: str = ""
    sample_id: str = ""
    test_type: str = "3PT"          # "3PT" | "TENSILE"
    geometry: str = "rectangular"   # "rectangular" | "circular" | "hollow"

    # rectangular
    width_mm: float = 0.0           # b
    thickness_mm: float = 0.0       # d

    # circular solid
    diameter_mm: float = 0.0        # d

    # hollow tube
    outer_dia_mm: float = 0.0       # D
    inner_dia_mm: float = 0.0       # d (inner)

    # 3-point bend
    span_mm: float = 0.0            # L (support span)

    # tensile
    gauge_length_mm: float = 0.0    # L₀

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
        """Second moment of area I about the neutral axis (bending)."""
        if self.geometry == "rectangular":
            return (self.width_mm * self.thickness_mm ** 3) / 12.0
        if self.geometry == "circular":
            return math.pi * self.diameter_mm ** 4 / 64.0
        if self.geometry == "hollow":
            return math.pi * (self.outer_dia_mm ** 4 - self.inner_dia_mm ** 4) / 64.0
        return 0.0

    def outer_fibre_distance_mm(self) -> float:
        """Distance c from neutral axis to extreme fibre (for flexural stress)."""
        if self.geometry == "rectangular":
            return self.thickness_mm / 2.0
        if self.geometry == "circular":
            return self.diameter_mm / 2.0
        if self.geometry == "hollow":
            return self.outer_dia_mm / 2.0
        return 0.0

    def is_valid_for_test(self) -> tuple[bool, str]:
        """Returns (ok, reason). reason is empty string when ok."""
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
    peak_load_kg: float = 0.0
    peak_load_N: float = 0.0
    peak_displacement_mm: float = 0.0
    flexural_stress_MPa: Optional[float] = None     # at peak
    flexural_strain_peak: Optional[float] = None    # at peak (dimensionless)
    flexural_modulus_GPa: Optional[float] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class TensileResults:
    peak_load_kg: float = 0.0
    peak_load_N: float = 0.0
    peak_displacement_mm: float = 0.0
    cross_section_area_mm2: Optional[float] = None
    uts_MPa: Optional[float] = None                 # ultimate tensile strength
    strain_at_peak: Optional[float] = None
    youngs_modulus_GPa: Optional[float] = None
    yield_strength_MPa: Optional[float] = None      # 0.2 % offset (best-effort)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _linear_slope_through_origin(x: np.ndarray, y: np.ndarray) -> float:
    """Least-squares slope of y = k*x forced through the origin."""
    denom = float(np.dot(x, x))
    if denom == 0:
        return 0.0
    return float(np.dot(x, y)) / denom


def _find_linear_region_mask(
    disp: np.ndarray, load: np.ndarray, fraction: float = 0.4
) -> np.ndarray:
    """Boolean mask covering the initial linear region (first `fraction` of disp range)."""
    if len(disp) < 3:
        return np.ones(len(disp), dtype=bool)
    cutoff = disp[0] + fraction * (disp[-1] - disp[0])
    mask = disp <= cutoff
    # Need at least 3 points; if not, widen the window
    if mask.sum() < 3:
        mask = np.zeros(len(disp), dtype=bool)
        mask[:3] = True
    return mask


def _yield_strength_02_offset(
    strain: np.ndarray,
    stress: np.ndarray,
    E_MPa: float,
) -> Optional[float]:
    """0.2 % offset yield strength.  Returns None if the curve doesn't cross the offset line."""
    offset_stress = E_MPa * (strain - 0.002)
    diff = stress - offset_stress
    # Find sign change
    for i in range(len(diff) - 1):
        if diff[i] <= 0 < diff[i + 1] or diff[i] >= 0 > diff[i + 1]:
            # Linear interpolation
            t = -diff[i] / (diff[i + 1] - diff[i])
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

    res.peak_load_kg = float(np.max(load))
    res.peak_load_N = res.peak_load_kg * G
    peak_idx = int(np.argmax(load))
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

    # Flexural stress at peak  σ = M·c/I,  M = F·L/4
    M_peak = res.peak_load_N * L / 4.0
    res.flexural_stress_MPa = M_peak * c / I          # [N·mm / mm⁴ · mm] = N/mm² = MPa

    # Flexural strain at peak  ε = 12·δ·c / L²
    res.flexural_strain_peak = 12.0 * res.peak_displacement_mm * c / (L ** 2)

    # Flexural modulus from linear region slope
    mask = _find_linear_region_mask(disp, load)
    if mask.sum() >= 3:
        slope_kg_per_mm = _linear_slope_through_origin(disp[mask], load[mask])
        slope_N_per_mm = slope_kg_per_mm * G
        # E = L³ / (48·I) · dF/dδ   [mm³/mm⁴ · N/mm] = N/mm² = MPa
        E_MPa = (L ** 3 / (48.0 * I)) * slope_N_per_mm
        res.flexural_modulus_GPa = E_MPa / 1000.0
        res.notes.append("Modulus from first 40 % of displacement range.")
    else:
        res.notes.append("Too few points to calculate modulus.")

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

    res.peak_load_kg = float(np.max(load))
    res.peak_load_N = res.peak_load_kg * G
    peak_idx = int(np.argmax(load))
    res.peak_displacement_mm = float(disp[peak_idx])

    ok, reason = specimen.is_valid_for_test()
    if not ok:
        res.notes.append(f"Cannot calculate properties: {reason}")
        return res

    A = specimen.cross_section_area_mm2()
    L0 = specimen.gauge_length_mm

    if A <= 0:
        res.notes.append("Invalid cross-section area (A = 0).")
        return res

    res.cross_section_area_mm2 = A

    # UTS
    res.uts_MPa = res.peak_load_N / A

    # Strain at peak
    res.strain_at_peak = res.peak_displacement_mm / L0

    # Stress and strain arrays for modulus calculation
    stress = load * G / A           # MPa
    strain = disp / L0

    mask = _find_linear_region_mask(disp, load)
    if mask.sum() >= 3:
        E_MPa = _linear_slope_through_origin(strain[mask], stress[mask])
        res.youngs_modulus_GPa = E_MPa / 1000.0
        res.notes.append("Modulus from first 40 % of displacement range.")

        # 0.2 % offset yield strength
        res.yield_strength_MPa = _yield_strength_02_offset(strain, stress, E_MPa)
        if res.yield_strength_MPa is not None:
            res.notes.append("Yield strength via 0.2 % offset method.")
        else:
            res.notes.append("0.2 % offset yield point not found in data.")
    else:
        res.notes.append("Too few points to calculate modulus.")

    return res
