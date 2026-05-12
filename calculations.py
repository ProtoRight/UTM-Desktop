"""Mechanical property calculations for 3-point bend and tensile tests.

Data preprocessing
------------------
trim_errant_start   — removes stale pre-test displacement readings; the first
                      RUNNING packet arrives before the Arduino zeroes the DRO,
                      so displacement may be positive or negative from prior
                      movement.  Looks for the first near-zero point in the
                      opening window and discards everything before it.
offset_to_zero      — subtracts the first point's displacement so x starts at 0

Linear region detection
-----------------------
Uses a line-through-origin fit with R² threshold (default 0.995).
Expands the linear window one point at a time from the onset of loading.
Falls back to the first 40 % of data if the detected region is too small.
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
# Linear region detection (R²-based, line through origin)
# ---------------------------------------------------------------------------

def _r2_through_origin(x: np.ndarray, y: np.ndarray) -> float:
    """R² of y = k·x (forced through origin)."""
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return 0.0
    slope = float(np.dot(x, y)) / denom
    y_pred = slope * x
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    if ss_tot < 1e-10:
        return 1.0
    return 1.0 - ss_res / ss_tot


def _find_linear_region(
    x: np.ndarray,
    y: np.ndarray,
    r2_threshold: float = 0.995,
    min_pts: int = 5,
    fallback_fraction: float = 0.40,
) -> np.ndarray:
    """Return boolean mask of the initial linear region.

    Algorithm:
    1. Skip the initial noise toe (load < 1 % of peak) to avoid fitting noise.
    2. Expand the window one point at a time while R² ≥ threshold.
    3. If the detected region is < 5 % of the displacement range, fall back to
       the first `fallback_fraction` of data.
    """
    n = len(x)
    if n < min_pts:
        return np.ones(n, dtype=bool)

    peak_y = float(np.max(y))
    if peak_y <= 0:
        return np.ones(n, dtype=bool)

    # Find onset of loading (first point where load ≥ 1 % of peak)
    onset = 0
    for i in range(n):
        if y[i] >= peak_y * 0.01:
            onset = i
            break

    if n - onset < min_pts:
        cutoff = x[0] + fallback_fraction * (x[-1] - x[0])
        return x <= cutoff

    # Grow linear window.
    # Shift both x and y to the onset point so the origin-forced fit represents
    # Δload vs Δdisp from first contact.  Without the y-shift, a non-zero onset
    # load (specimen already under ~1 % of peak at the threshold) causes the
    # forced-origin R² to fail immediately, capping the window at min_pts.
    # Skip the onset point itself in the loop: it has (Δx=0, Δy=0) by definition
    # and contributes nothing to the fit.
    x_onset = float(x[onset])
    y_onset = float(y[onset])
    best_end = onset + min_pts
    for end in range(onset + min_pts + 1, n + 1):
        xi = x[onset + 1:end] - x_onset   # Δdisp from contact onset
        yi = y[onset + 1:end] - y_onset   # Δload from contact onset
        if len(xi) < 2:
            best_end = end
            continue
        r2 = _r2_through_origin(xi, yi)
        if r2 >= r2_threshold:
            best_end = end
        else:
            break

    # Sanity check: is the linear region at least 5 % of the *post-contact* range?
    # Using x[-1]-x[0] (total range including run-up) would make the threshold
    # grow with run-up length, causing spurious fallbacks on long approach strokes.
    x_post_onset = float(x[-1] - x[onset])
    if x_post_onset > 0 and (float(x[best_end - 1]) - x_onset) < 0.05 * x_post_onset:
        cutoff = x_onset + fallback_fraction * x_post_onset
        mask = (x >= x[onset]) & (x <= cutoff)
        return mask

    mask = np.zeros(n, dtype=bool)
    mask[onset:best_end] = True
    return mask


def _slope_through_origin(x: np.ndarray, y: np.ndarray) -> float:
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(x, y)) / denom


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

    # Flexural modulus from linear region
    mask = _find_linear_region(disp, load)
    n_lin = int(mask.sum())
    if n_lin >= 5:
        onset_idx = int(np.where(mask)[0][0])
        disp_off  = float(disp[onset_idx])
        load_off  = float(load[onset_idx])
        # Shift both x and y to the onset point: slope = Δload/Δdisp from contact.
        slope_kg_per_mm = _slope_through_origin(
            disp[mask] - disp_off, load[mask] - load_off
        )
        slope_N_per_mm  = slope_kg_per_mm * G
        # E = L³/(48·I) · (dF/dδ)
        E_MPa = (L ** 3 / (48.0 * I)) * slope_N_per_mm
        res.flexural_modulus_GPa          = E_MPa / 1000.0
        res.linear_region_onset_mm        = disp_off
        res.linear_region_onset_load_kg   = float(load[onset_idx])
        res.linear_region_end_mm          = float(disp[mask][-1])
        res.linear_region_slope_kg_per_mm = slope_kg_per_mm
        res.notes.append(
            f"Flexural modulus from linear region "
            f"({disp_off:.2f} – {res.linear_region_end_mm:.2f} mm, "
            f"{n_lin} pts, R²≥0.995)."
        )
    else:
        res.notes.append("Too few points in linear region — modulus not calculated.")

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

    # Modulus from linear region
    mask = _find_linear_region(disp, load)
    n_lin = int(mask.sum())
    if n_lin >= 5:
        onset_idx  = int(np.where(mask)[0][0])
        disp_off   = float(disp[onset_idx])
        stress_off = float(stress[onset_idx])
        # Shift both Δstrain and Δstress to onset so the origin-forced fit
        # gives the true dσ/dε from the contact point, not from machine zero.
        strain_shifted = (disp[mask] - disp_off) / L0
        stress_shifted = stress[mask] - stress_off
        E_MPa = _slope_through_origin(strain_shifted, stress_shifted)
        res.youngs_modulus_GPa            = E_MPa / 1000.0
        res.linear_region_onset_mm        = disp_off
        res.linear_region_onset_load_kg   = float(load[onset_idx])
        res.linear_region_end_mm          = float(disp[mask][-1])
        res.linear_region_slope_kg_per_mm = E_MPa * A / (G * L0)
        res.notes.append(
            f"Young's modulus from linear region "
            f"({disp_off:.2f} – {res.linear_region_end_mm:.2f} mm, "
            f"{n_lin} pts, R²≥0.995)."
        )

        # 0.2 % offset yield strength (offset from contact onset, not machine zero)
        onset_strain = disp_off / L0
        res.yield_strength_MPa = _yield_02_offset(strain, stress, E_MPa, onset_strain)
        if res.yield_strength_MPa is not None:
            res.notes.append("Yield strength via 0.2 % offset method.")
        else:
            res.notes.append("0.2 % offset yield point not found in data.")
    else:
        res.notes.append("Too few points in linear region — modulus not calculated.")

    return res
