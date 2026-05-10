"""Unit conversion utilities.

Internal data is always stored in kg (load) and mm (displacement).
These functions convert TO display units at render time.
"""

from __future__ import annotations
from enum import Enum


class LoadUnit(Enum):
    KG  = "kg"
    N   = "N"
    LBF = "lbf"


class DispUnit(Enum):
    MM   = "mm"
    INCH = "in"


class ResultsUnit(Enum):
    METRIC   = "Metric"
    IMPERIAL = "Imperial"


# --- Load conversions (from kg) ---
_KG_TO: dict[LoadUnit, float] = {
    LoadUnit.KG:  1.0,
    LoadUnit.N:   9.80665,
    LoadUnit.LBF: 2.20462,
}

# --- Displacement conversions (from mm) ---
_MM_TO: dict[DispUnit, float] = {
    DispUnit.MM:   1.0,
    DispUnit.INCH: 1.0 / 25.4,
}

# --- Results conversions (from SI: MPa, GPa, mm, N) ---
#   Stress:   MPa  →  ksi    (1 MPa = 0.145038 ksi)
#   Modulus:  GPa  →  Msi    (1 GPa = 0.145038 Msi)
#   Load:     N    →  lbf    (1 N   = 0.224809 lbf)
#   Disp:     mm   →  inches
MPa_TO_KSI  = 0.145038
GPa_TO_MSI  = 0.145038
N_TO_LBF    = 0.224809
MM_TO_INCH  = 1.0 / 25.4


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def kg_to(value: float, unit: LoadUnit) -> float:
    return value * _KG_TO[unit]


def mm_to(value: float, unit: DispUnit) -> float:
    return value * _MM_TO[unit]


def load_unit_label(unit: LoadUnit) -> str:
    return unit.value


def disp_unit_label(unit: DispUnit) -> str:
    return unit.value


# Results unit labels
RESULTS_LABELS: dict[ResultsUnit, dict[str, str]] = {
    ResultsUnit.METRIC: {
        "stress":  "MPa",
        "modulus": "GPa",
        "load":    "N",
        "disp":    "mm",
        "load_raw": "kg",
    },
    ResultsUnit.IMPERIAL: {
        "stress":  "ksi",
        "modulus": "Msi",
        "load":    "lbf",
        "disp":    "in",
        "load_raw": "lbf",
    },
}


def convert_results_load(load_N: float, unit: ResultsUnit) -> float:
    if unit == ResultsUnit.METRIC:
        return load_N
    return load_N * N_TO_LBF


def convert_results_stress(stress_MPa: float, unit: ResultsUnit) -> float:
    if unit == ResultsUnit.METRIC:
        return stress_MPa
    return stress_MPa * MPa_TO_KSI


def convert_results_modulus(modulus_GPa: float, unit: ResultsUnit) -> float:
    if unit == ResultsUnit.METRIC:
        return modulus_GPa
    return modulus_GPa * GPa_TO_MSI


def convert_results_disp(disp_mm: float, unit: ResultsUnit) -> float:
    if unit == ResultsUnit.METRIC:
        return disp_mm
    return disp_mm * MM_TO_INCH
